"""One focused integration test proving the Person 4 <-> index engine handoff:

    raw scraper-shaped data
        -> validate_fare_batch()
        -> quality_result.valid_observations
        -> AirfarePriceIndex.calculate()
        -> successful index result

Does not touch either module's methodology: the engine runs with its own
default IndexConfig (median representative fare, default IQR outlier
detection), and data_quality runs with its own default DataQualityConfig.
"""

from __future__ import annotations

import pandas as pd
import pytest

from conftest import make_observation
from data_quality import validate_fare_batch
from data_quality import reason_codes as rc
from index_engine import AirfarePriceIndex


def test_valid_and_flagged_reach_engine_rejected_does_not():
    """Deterministic 8-record batch: 6 structurally valid, 1 flagged
    (SUSPICIOUS_FARE — still expected to reach the engine), 1 rejected
    (NON_POSITIVE_FARE — must never reach the engine).

    The flagged record's fare is deliberately extreme enough that the
    index engine's own default IQR outlier detection excludes it from the
    representative-fare calculation, which is exactly the documented
    separation of concerns: data_quality flags for attention, the index
    engine's own statistics make the final call on exclusion.
    """
    base_period_obs = [
        make_observation(
            observation_id=f"BASE{i}",
            flight_date="2026-01-15",
            booking_date="2026-01-01",
            total_fare=fare,
        )
        for i, fare in enumerate([5000, 5100, 5200])
    ]

    current_period_valid = [
        make_observation(
            observation_id=f"CUR{i}",
            flight_date=flight_date,
            booking_date="2026-02-01",
            total_fare=fare,
        )
        for i, (flight_date, fare) in enumerate(
            [("2026-02-10", 5200), ("2026-02-15", 5300), ("2026-02-20", 5400)]
        )
    ]

    flagged_obs = make_observation(
        observation_id="CUR_SUSPICIOUS",
        flight_date="2026-02-12",
        booking_date="2026-02-01",
        total_fare=8000,  # SUSPICIOUS_FARE under data_quality's wide sanity net
    )

    rejected_obs = make_observation(
        observation_id="CUR_BAD",
        flight_date="2026-02-25",
        booking_date="2026-02-01",
        total_fare=-100,  # NON_POSITIVE_FARE
    )

    raw_data = base_period_obs + current_period_valid + [flagged_obs, rejected_obs]
    assert len(raw_data) == 8

    # --- Step 1: data quality layer ----------------------------------
    quality_result = validate_fare_batch(raw_data)

    assert quality_result.records_received == 8
    assert quality_result.records_rejected == 1
    assert quality_result.records_flagged == 1
    assert quality_result.records_valid == 6
    assert quality_result.rejection_reasons == {rc.NON_POSITIVE_FARE: 1}
    assert quality_result.flag_reasons.get(rc.SUSPICIOUS_FARE) == 1

    valid_ids = {o["observation_id"] for o in quality_result.valid_observations}
    # Rejected record must NOT reach the index.
    assert "CUR_BAD" not in valid_ids
    # Flagged record MUST still reach the index.
    assert "CUR_SUSPICIOUS" in valid_ids
    assert len(quality_result.valid_observations) == 7

    # --- Step 2: hand straight to the frozen index engine, no translation ---
    engine = AirfarePriceIndex(base_period="2026-01")  # engine's own defaults, untouched
    index_result = engine.calculate(
        observations=quality_result.valid_observations,
        current_period="2026-02",
    )

    # The rejected record never even reached the engine's input.
    assert index_result.observations_received == 7

    # --- Step 3: independently compute the expected index -------------
    # Base period (3 points, below the engine's outlier-check minimum
    # group size of 4): median of [5000, 5100, 5200].
    expected_base_fare = 5100.0
    # Current period (4 points reach the engine: 3 normal + the flagged
    # 8000 spike). The engine's own default IQR outlier detector
    # (1.5x IQR) excludes 8000 from this group before taking the median —
    # verified independently: q1=5275, q3=6050, iqr=775,
    # upper bound = 6050 + 1.5*775 = 7212.5 < 8000.
    expected_current_fare = 5300.0  # median of surviving [5200, 5300, 5400]
    expected_route_index = 100.0 * expected_current_fare / expected_base_fare

    assert index_result.national_index == pytest.approx(expected_route_index)
    assert len(index_result.route_indices) == 1
    route = index_result.route_indices[0]
    assert route.route == "BLR-DEL"
    assert route.route_index == pytest.approx(expected_route_index)
    assert route.base_period_fare == pytest.approx(expected_base_fare)
    assert route.period_fare == pytest.approx(expected_current_fare)
    # Only 3 of the 4 current-period observations that reached the engine
    # survive its own outlier detection into the representative fare.
    assert route.observations_used == 3
    assert route.status == "OK"

    # The 8000 spike shows up in the engine's own cleaning report as an
    # outlier it removed — proof it really did reach the engine's pipeline
    # (as data_quality's FLAGGED status promised) rather than being
    # silently dropped somewhere in the handoff.
    assert index_result.cleaning_report.removed_by_reason.get("OUTLIER_IQR") == 1
