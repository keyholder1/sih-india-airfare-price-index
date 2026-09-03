import pandas as pd
import pytest

from conftest import make_observation, to_df
from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.exceptions import InsufficientDataError
from index_engine.quality import (
    STATUS_DISCONTINUED,
    STATUS_INSUFFICIENT_DATA,
    STATUS_NEW_ROUTE,
    STATUS_OK,
)

EMPTY_SCHEMA_COLUMNS = [
    "observation_id", "airline", "origin", "destination", "flight_date",
    "booking_date", "total_fare", "currency",
]


def _route_rows(origin, destination, period_day, fare, n=5, **overrides):
    return [
        make_observation(
            origin=origin,
            destination=destination,
            flight_date=period_day,
            booking_date=pd.Timestamp(period_day) - pd.Timedelta(days=10),
            total_fare=fare + i,  # tiny spread so it's not a degenerate single value
            **overrides,
        )
        for i in range(n)
    ]


def test_known_route_and_national_index_manual_calculation():
    """5000 -> 5500 on the only route in the index must give index = 110."""
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    assert result.routes_covered == 1
    route = result.route_indices[0]
    assert route.status == STATUS_OK
    assert abs(route.route_index - 110.0) < 0.5
    assert abs(result.national_index - 110.0) < 0.5


def test_weighted_national_index_matches_manual_calculation():
    rows = (
        _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
        + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)  # index ~110
        + _route_rows("DEL", "BOM", "2026-01-15", 5000.0)
        + _route_rows("DEL", "BOM", "2026-08-15", 5250.0)  # index ~105
    )
    weights = pd.DataFrame(
        {"origin": ["BLR", "DEL"], "destination": ["DEL", "BOM"], "weight": [3.0, 1.0]}
    )
    engine = AirfarePriceIndex(base_period="2026-01", weights=weights)
    result = engine.calculate(to_df(rows), current_period="2026-08")
    # 110*0.75 + 105*0.25 = 108.75
    assert abs(result.national_index - 108.75) < 0.5


def test_mom_and_yoy_change_calculation():
    rows = (
        _route_rows("BLR", "DEL", "2025-08-15", 5200.0)  # prev year
        + _route_rows("BLR", "DEL", "2026-01-15", 5000.0)  # base
        + _route_rows("BLR", "DEL", "2026-07-15", 5300.0)  # prev month
        + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)  # current
    )
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")

    expected_mom = (110.0 / 106.0 - 1) * 100
    expected_yoy = (110.0 / 104.0 - 1) * 100
    assert abs(result.mom_change_pct - expected_mom) < 0.5
    assert abs(result.yoy_change_pct - expected_yoy) < 0.5


def test_route_contributions_sum_to_national_index_change_for_arithmetic_aggregation():
    rows = (
        _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
        + _route_rows("BLR", "DEL", "2026-07-15", 5200.0)
        + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)
        + _route_rows("DEL", "BOM", "2026-01-15", 5000.0)
        + _route_rows("DEL", "BOM", "2026-07-15", 5100.0)
        + _route_rows("DEL", "BOM", "2026-08-15", 5150.0)
    )
    engine = AirfarePriceIndex(base_period="2026-01", config=IndexConfig(base_period="2026-01", aggregation_method="arithmetic"))
    result = engine.calculate(to_df(rows), current_period="2026-08")

    total_contribution = sum(c.contribution_points for c in result.route_contributions if c.contribution_points is not None)
    # For arithmetic aggregation, contributions must exactly reconstruct the MoM point change.
    prev_month_national = result.national_index / (1 + result.mom_change_pct / 100)
    assert abs(total_contribution - (result.national_index - prev_month_national)) < 0.5


def test_observations_used_excludes_rows_with_invalid_non_default_fare_field():
    good_rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0, n=5)
    bad_row = make_observation(
        origin="BLR", destination="DEL", flight_date="2026-01-15",
        booking_date="2026-01-01", total_fare=5000.0, base_fare=None,
    )
    engine = AirfarePriceIndex(
        base_period="2026-01",
        config=IndexConfig(base_period="2026-01", fare_field="base_fare", min_observations_per_route_period=1),
    )
    result = engine.calculate(to_df(good_rows + [bad_row]), current_period="2026-01")
    # The bad_fare row is rejected at validation, not silently counted as
    # "used" while contributing nothing to the median.
    assert result.observations_used == 5
    assert result.cleaning_report.total_valid == 5
    assert result.cleaning_report.removed_by_reason.get("INVALID_FARE") == 1


def test_weight_basket_is_anchored_to_base_period_not_current_period():
    # DEL-BOM's weight only becomes effective from 2026-06 onward -- as of
    # base_period (2026-01) it must NOT be part of the fixed weight
    # basket, even though current_period (2026-08) is well past its
    # effective_from date. If the basket were (incorrectly) selected as of
    # current_period instead of base_period, DEL-BOM would be included and
    # would get a non-None weight_normalized.
    rows = (
        _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
        + _route_rows("BLR", "DEL", "2026-08-15", 5000.0)
        + _route_rows("DEL", "BOM", "2026-01-15", 5000.0)
        + _route_rows("DEL", "BOM", "2026-08-15", 5000.0)
    )
    weights = pd.DataFrame(
        [
            {"origin": "BLR", "destination": "DEL", "weight": 0.5, "effective_from": None, "effective_to": None},
            {"origin": "DEL", "destination": "BOM", "weight": 0.5, "effective_from": "2026-06-01", "effective_to": None},
        ]
    )
    engine = AirfarePriceIndex(base_period="2026-01", weights=weights, config=IndexConfig(base_period="2026-01"))
    result = engine.calculate(to_df(rows), current_period="2026-08")

    by_route = {r.route: r for r in result.route_indices}
    assert by_route["DEL-BOM"].weight_normalized is None
    # BLR-DEL is the only route left in the basket -> renormalized to 1.0.
    assert by_route["BLR-DEL"].weight_normalized == pytest.approx(1.0)
    # The national index is therefore driven entirely by BLR-DEL.
    assert result.national_index == pytest.approx(by_route["BLR-DEL"].route_index)


def test_new_route_has_no_index_but_is_flagged():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("CCU", "DEL", "2026-08-15", 4000.0)
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    new_route = next(r for r in result.route_indices if r.route == "CCU-DEL")
    assert new_route.status == STATUS_NEW_ROUTE
    assert new_route.route_index is None


def test_discontinued_route_has_no_index_but_is_flagged():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-08-15", 5500.0) + _route_rows(
        "CCU", "DEL", "2026-01-15", 4000.0
    )
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    discontinued = next(r for r in result.route_indices if r.route == "CCU-DEL")
    assert discontinued.status == STATUS_DISCONTINUED
    assert discontinued.route_index is None


def test_insufficient_observations_is_flagged_not_silently_used():
    rows = (
        _route_rows("BLR", "DEL", "2026-01-15", 5000.0, n=2)  # below default min of 3
        + _route_rows("BLR", "DEL", "2026-08-15", 5500.0, n=5)
    )
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    route = result.route_indices[0]
    assert route.status == STATUS_INSUFFICIENT_DATA
    assert route.route_index is None


def test_all_zero_weights_degrade_to_none_national_index_not_a_crash():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)
    weights = pd.DataFrame({"origin": ["BLR"], "destination": ["DEL"], "weight": [0.0]})
    engine = AirfarePriceIndex(base_period="2026-01", weights=weights)
    result = engine.calculate(to_df(rows), current_period="2026-08")
    assert result.national_index is None
    assert result.route_indices[0].status == STATUS_OK  # the route itself still computes fine
    assert result.route_indices[0].weight_normalized == 0.0


def test_empty_dataset_raises_insufficient_data_error():
    empty_df = pd.DataFrame(columns=EMPTY_SCHEMA_COLUMNS)
    engine = AirfarePriceIndex(base_period="2026-01")
    with pytest.raises(InsufficientDataError):
        engine.calculate(empty_df, current_period="2026-08")


def test_no_valid_observations_raises_insufficient_data_error():
    rows = [make_observation(total_fare=-1) for _ in range(5)]  # all invalid
    engine = AirfarePriceIndex(base_period="2026-01")
    with pytest.raises(InsufficientDataError):
        engine.calculate(to_df(rows), current_period="2026-08")


def test_booking_horizon_filter_changes_representative_fare():
    last_minute = [
        make_observation(
            flight_date="2026-08-15",
            booking_date="2026-08-13",  # 2-day horizon -> bucket "0-3"
            total_fare=8000.0 + i,
        )
        for i in range(5)
    ]
    advance = [
        make_observation(
            flight_date="2026-08-15",
            booking_date="2026-06-15",  # 61-day horizon -> bucket "61+"
            total_fare=4000.0 + i,
        )
        for i in range(5)
    ]
    base = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)

    engine_all = AirfarePriceIndex(base_period="2026-01")
    result_all = engine_all.calculate(to_df(base + last_minute + advance), current_period="2026-08")

    engine_last_minute = AirfarePriceIndex(
        base_period="2026-01", config=IndexConfig(base_period="2026-01", booking_horizon_filter="0-3")
    )
    result_filtered = engine_last_minute.calculate(to_df(base + last_minute + advance), current_period="2026-08")

    assert result_filtered.route_indices[0].period_fare > result_all.route_indices[0].period_fare


def test_contribution_reconciliation_flag_when_route_status_changes_between_periods():
    """A route that is OK this month but INSUFFICIENT_DATA last month breaks
    the exact contribution-sum-to-MoM-change identity; the engine must say
    so rather than silently under-count."""
    rows = (
        _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
        + _route_rows("BLR", "DEL", "2026-07-15", 5100.0, n=2)  # below min_observations -> INSUFFICIENT_DATA
        + _route_rows("BLR", "DEL", "2026-08-15", 5500.0, n=5)  # OK this month
    )
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    assert any("contribution decomposition is partial" in flag for flag in result.quality_flags)


def test_yoy_reconciliation_flag_when_route_status_changes_between_periods():
    """Same compositional-change issue as MoM (see the preceding test), but
    for the prev-year comparison — previously ungated, now flagged."""
    rows = (
        _route_rows("BLR", "DEL", "2025-08-15", 5000.0, n=2)  # below min_observations -> INSUFFICIENT_DATA a year ago
        + _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
        + _route_rows("BLR", "DEL", "2026-08-15", 5500.0, n=5)  # OK this month
    )
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    assert any("YoY reflects a partial change in route composition" in flag for flag in result.quality_flags)


def test_quality_metric_aliases_are_consistent():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)
    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(to_df(rows), current_period="2026-08")
    assert result.routes_expected == result.routes_total
    assert result.observations_received == result.cleaning_report.total_input
    assert result.observations_rejected == result.cleaning_report.total_removed
    assert result.outliers_flagged == 0
    assert result.routes_with_data == 1


def test_multiple_airlines_and_fare_classes_are_pooled_into_one_route_period_fare():
    rows = [
        make_observation(flight_date="2026-01-15", booking_date="2026-01-01", airline="IndiGo", fare_class="Economy", total_fare=5000.0),
        make_observation(flight_date="2026-01-16", booking_date="2026-01-02", airline="Vistara", fare_class="PremiumEconomy", total_fare=5100.0),
        make_observation(flight_date="2026-01-17", booking_date="2026-01-03", airline="AirIndia", fare_class="Economy", total_fare=4900.0),
    ]
    engine = AirfarePriceIndex(base_period="2026-01")
    # Reuse the same rows as "current period" too so the index is computable end to end.
    current_rows = [dict(r, observation_id=r["observation_id"] + "_cur", flight_date="2026-08-" + r["flight_date"][-2:]) for r in rows]
    result = engine.calculate(to_df(rows + current_rows), current_period="2026-08")
    assert result.route_indices[0].observations_used == 3
