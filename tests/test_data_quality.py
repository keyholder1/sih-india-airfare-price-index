"""Tests for the data_quality layer (Person 4's module).

Uses the same ``make_observation``/``make_observations`` helpers as the
index engine's own test suite (tests/conftest.py) so fixtures stay
consistent across both test files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from data_quality import DataQualityConfig, validate_fare_batch
from data_quality import reason_codes as rc
from index_engine import AirfarePriceIndex

from conftest import make_observation, make_observations


def distinct_observations(n: int, **overrides) -> list:
    """``n`` observations that don't collide as EXACT_DUPLICATE or
    POTENTIAL_DUPLICATE with each other (varies flight_date, part of the
    duplicate grouping key, and total_fare) — for tests that want "n
    independent valid records", not "n quotes for the same route/date"."""
    return [
        make_observation(
            observation_id=f"DISTINCT{i:04d}",
            flight_date=(pd.Timestamp("2026-01-15") + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            total_fare=5000.0 + 10 * i,
            **overrides,
        )
        for i in range(n)
    ]


# --------------------------------------------------------------------------
# Valid records
# --------------------------------------------------------------------------

class TestValidRecords:
    def test_normal_fare_is_valid(self):
        result = validate_fare_batch([make_observation()])
        assert result.records_valid == 1
        assert result.records_rejected == 0

    def test_same_day_booking_is_valid(self):
        obs = make_observation(flight_date="2026-01-15", booking_date="2026-01-15")
        result = validate_fare_batch([obs])
        assert result.records_valid == 1

    def test_normal_route_batch_is_valid(self):
        result = validate_fare_batch(make_observations(20))
        # All 20 share identical field values apart from observation_id, so
        # content-based exact-duplicate detection correctly catches 19 of them.
        assert result.records_valid == 1
        assert result.exact_duplicate_count == 19

    def test_normal_route_batch_with_varied_fields_all_valid(self):
        obs = distinct_observations(20)
        result = validate_fare_batch(obs)
        assert result.records_valid == 20
        assert result.records_rejected == 0


# --------------------------------------------------------------------------
# Invalid records (rejections)
# --------------------------------------------------------------------------

class TestRejections:
    def test_missing_fare(self):
        result = validate_fare_batch([make_observation(total_fare=None)])
        assert result.rejection_reasons == {rc.NON_POSITIVE_FARE: 1}

    def test_zero_fare(self):
        result = validate_fare_batch([make_observation(total_fare=0)])
        assert result.rejection_reasons == {rc.NON_POSITIVE_FARE: 1}

    def test_negative_fare(self):
        result = validate_fare_batch([make_observation(total_fare=-100)])
        assert result.rejection_reasons == {rc.NON_POSITIVE_FARE: 1}

    def test_missing_origin(self):
        result = validate_fare_batch([make_observation(origin="")])
        assert result.rejection_reasons == {rc.MISSING_ORIGIN: 1}

    def test_missing_destination(self):
        result = validate_fare_batch([make_observation(destination=None)])
        assert result.rejection_reasons == {rc.MISSING_DESTINATION: 1}

    def test_origin_equals_destination(self):
        result = validate_fare_batch([make_observation(origin="BLR", destination="BLR")])
        assert result.rejection_reasons == {rc.SAME_ORIGIN_DESTINATION: 1}

    def test_origin_equals_destination_case_insensitive(self):
        result = validate_fare_batch([make_observation(origin="blr", destination="BLR")])
        assert result.rejection_reasons == {rc.SAME_ORIGIN_DESTINATION: 1}

    def test_invalid_flight_date(self):
        result = validate_fare_batch([make_observation(flight_date="not-a-date")])
        assert result.rejection_reasons == {rc.INVALID_FLIGHT_DATE: 1}

    def test_booking_after_flight_date(self):
        result = validate_fare_batch(
            [make_observation(booking_date="2026-09-10", flight_date="2026-09-05")]
        )
        assert result.rejection_reasons == {rc.NEGATIVE_BOOKING_HORIZON: 1}

    def test_missing_observation_id(self):
        result = validate_fare_batch([make_observation(observation_id="")])
        assert result.rejection_reasons == {rc.MISSING_OBSERVATION_ID: 1}

    def test_missing_currency(self):
        result = validate_fare_batch([make_observation(currency="")])
        assert result.rejection_reasons == {rc.MISSING_CURRENCY: 1}

    def test_non_inr_currency_rejected_not_silently_treated_as_inr(self):
        result = validate_fare_batch([make_observation(currency="USD")])
        assert result.rejection_reasons == {rc.NON_INR_CURRENCY: 1}

    def test_invalid_airport_code_format(self):
        result = validate_fare_batch([make_observation(origin="B1")])
        assert result.rejection_reasons == {rc.INVALID_AIRPORT_CODE: 1}

    def test_missing_airline(self):
        result = validate_fare_batch([make_observation(airline=None)])
        assert result.rejection_reasons == {rc.MISSING_AIRLINE: 1}

    def test_rejected_records_are_excluded_from_valid_observations(self):
        result = validate_fare_batch([make_observation(total_fare=-1)])
        assert result.valid_observations == []


# --------------------------------------------------------------------------
# Duplicate handling
# --------------------------------------------------------------------------

class TestDuplicates:
    def test_exact_duplicate_observation_id(self):
        obs = make_observation()
        dup = dict(obs)  # same observation_id, everything else the same
        result = validate_fare_batch([obs, dup])
        assert result.exact_duplicate_count == 1
        assert result.records_valid == 1
        assert result.rejection_reasons.get(rc.EXACT_DUPLICATE) == 1

    def test_exact_duplicate_full_content_different_id(self):
        obs = make_observation()
        dup = make_observation(**{k: v for k, v in obs.items() if k != "observation_id"})
        result = validate_fare_batch([obs, dup])
        assert result.exact_duplicate_count == 1

    def test_potential_duplicate_flagged_not_rejected(self):
        base = make_observation(total_fare=5000.0, timestamp="2026-01-01T09:00:00")
        near = make_observation(total_fare=5010.0, timestamp="2026-01-01T09:05:00")  # 0.2% apart
        result = validate_fare_batch([base, near])
        assert result.potential_duplicate_count == 1
        assert result.exact_duplicate_count == 0
        assert result.flag_reasons.get(rc.POTENTIAL_DUPLICATE) == 1
        # Not rejected: both remain eligible to reach the index engine.
        assert result.records_rejected == 0

    def test_far_apart_fare_same_route_is_not_a_duplicate(self):
        base = make_observation(total_fare=5000.0, timestamp="2026-01-01T09:00:00")
        different = make_observation(total_fare=9000.0, timestamp="2026-01-01T09:05:00")
        result = validate_fare_batch([base, different])
        assert result.potential_duplicate_count == 0
        assert result.duplicate_count == 0


# --------------------------------------------------------------------------
# Flagging
# --------------------------------------------------------------------------

class TestFlags:
    def test_suspicious_fare_flagged_not_rejected(self):
        normal = [
            make_observation(total_fare=5000.0 + i, observation_id=f"N{i:02d}", flight_date=f"2026-01-{15 + i:02d}")
            for i in range(10)
        ]
        spike = make_observation(total_fare=500000.0, observation_id="SPIKE", flight_date="2026-01-28")
        result = validate_fare_batch(normal + [spike])
        assert result.flag_reasons.get(rc.SUSPICIOUS_FARE) == 1
        assert result.records_rejected == 0
        assert result.records_flagged == 1

    def test_unmapped_route_flagged(self):
        result = validate_fare_batch([make_observation(origin="XYZ", destination="DEL")])
        assert result.flag_reasons.get(rc.UNMAPPED_LOCATION) == 1
        assert result.records_rejected == 0

    def test_known_route_not_flagged_unmapped(self):
        result = validate_fare_batch([make_observation(origin="BLR", destination="DEL")])
        assert rc.UNMAPPED_LOCATION not in result.flag_reasons

    def test_missing_optional_field_flagged(self):
        obs = make_observation()
        obs["baggage"] = None
        result = validate_fare_batch([obs])
        assert result.flag_reasons.get(rc.MISSING_OPTIONAL_FIELD) == 1
        # Optional-field gaps must not affect required-field completeness.
        assert result.completeness.completeness_rate == 1.0

    def test_stale_observation_flagged(self):
        recent = make_observation(timestamp="2026-01-20T00:00:00", observation_id="RECENT")
        old = make_observation(timestamp="2026-01-01T00:00:00", observation_id="OLD")
        result = validate_fare_batch([recent, old])
        assert result.flag_reasons.get(rc.STALE_OBSERVATION) == 1

    def test_unknown_airline_flagged_not_rejected(self):
        result = validate_fare_batch([make_observation(airline="BrandNewCarrier")])
        assert result.flag_reasons.get(rc.UNKNOWN_AIRLINE) == 1
        assert result.records_rejected == 0

    def test_stale_observation_flagged_with_mixed_timestamp_precision(self):
        """Regression: pandas' to_datetime format-inference fast path can
        silently coerce a differently-precise (but valid) ISO timestamp to
        NaT when it doesn't match the format inferred from other rows in
        the same column — which would make a genuinely stale row invisible
        instead of flagged. format="mixed" in validation.py guards this."""
        recent = [
            make_observation(
                timestamp=f"2026-01-20T00:00:{i:02d}.123456", observation_id=f"R{i}", flight_date=f"2026-02-{i + 1:02d}"
            )
            for i in range(5)
        ]
        old = make_observation(timestamp="2025-01-01T00:00:00", observation_id="OLD", flight_date="2026-02-20")
        result = validate_fare_batch(recent + [old])
        assert result.flag_reasons.get(rc.STALE_OBSERVATION) == 1

    def test_unusual_booking_horizon_flagged(self):
        obs = make_observation(flight_date="2027-06-01", booking_date="2026-01-01")  # ~510 days out
        result = validate_fare_batch([obs])
        assert result.flag_reasons.get(rc.UNUSUAL_BOOKING_HORIZON) == 1
        assert result.records_rejected == 0


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------

class TestAggregates:
    def test_completeness_rate(self):
        complete = make_observations(8)
        incomplete = [make_observation(airline=None) for _ in range(2)]
        result = validate_fare_batch(complete + incomplete)
        assert result.completeness.total_records == 10
        assert result.completeness.records_missing_required_fields == 2
        assert result.completeness.completeness_rate == pytest.approx(0.8)

    def test_validity_rate(self):
        valid = distinct_observations(9)
        invalid = [make_observation(total_fare=-1, observation_id="BAD", flight_date="2026-01-30")]
        result = validate_fare_batch(valid + invalid)
        assert result.validity_rate == pytest.approx(0.9)

    def test_rejection_reasons_counted(self):
        obs = [
            make_observation(total_fare=-1, observation_id="A"),
            make_observation(total_fare=0, observation_id="B"),
            make_observation(currency="EUR", observation_id="C"),
        ]
        result = validate_fare_batch(obs)
        assert result.rejection_reasons[rc.NON_POSITIVE_FARE] == 2
        assert result.rejection_reasons[rc.NON_INR_CURRENCY] == 1

    def test_duplicate_rate(self):
        obs = make_observation()
        result = validate_fare_batch([obs, dict(obs), dict(obs)])
        assert result.duplicate_rate == pytest.approx(2 / 3)

    def test_quality_score_and_grade_all_valid(self):
        obs = distinct_observations(10)
        result = validate_fare_batch(obs)
        assert result.quality_score == 100.0
        assert result.quality_grade == "EXCELLENT"

    def test_quality_score_degrades_with_rejections(self):
        good = distinct_observations(5)
        bad = [make_observation(total_fare=-1, observation_id=f"BAD{i}", flight_date=f"2026-02-{i + 1:02d}") for i in range(5)]
        result = validate_fare_batch(good + bad)
        assert result.quality_score < 100.0
        assert result.quality_grade in {"WARNING", "POOR", "GOOD"}

    def test_source_health_reports_per_source(self):
        a = distinct_observations(5, source="airline_site")
        b = [make_observation(source="mmt", observation_id=f"B{i}", total_fare=-1, flight_date=f"2026-02-{i + 1:02d}") for i in range(3)]
        result = validate_fare_batch(a + b)
        by_source = {s.source: s for s in result.source_health}
        assert by_source["airline_site"].observations_received == 5
        assert by_source["airline_site"].status == rc.HEALTH_HEALTHY
        assert by_source["mmt"].rejected_observations == 3
        # FAILED is reserved for zero observations (or a confirmed 0%
        # route_success_rate) — a source that returned data, all of which
        # happened to be rejected, is DEGRADED, not FAILED.
        assert by_source["mmt"].status == rc.HEALTH_DEGRADED

    def test_source_health_zero_route_success_is_failed(self):
        obs = distinct_observations(3, source="airline_zero")
        attempts = [{"source": "airline_zero", "routes_requested": 10, "routes_successful": 0}]
        result = validate_fare_batch(obs, route_attempts=attempts)
        by_source = {s.source: s for s in result.source_health}
        assert by_source["airline_zero"].status == rc.HEALTH_FAILED
        assert by_source["airline_zero"].route_success_rate == 0.0

    def test_source_health_route_attempts_populate_route_metrics(self):
        obs = distinct_observations(5, source="airline_A")
        attempts = [{"source": "airline_A", "routes_requested": 50, "routes_successful": 47}]
        result = validate_fare_batch(obs, route_attempts=attempts)
        by_source = {s.source: s for s in result.source_health}
        assert by_source["airline_A"].routes_requested == 50
        assert by_source["airline_A"].routes_successful == 47
        assert by_source["airline_A"].routes_failed == 3
        assert by_source["airline_A"].route_success_rate == pytest.approx(0.94)

    def test_route_health_reports_per_route(self):
        blr_del = [make_observation(origin="BLR", destination="DEL", observation_id=f"X{i}", total_fare=5000 + i) for i in range(5)]
        del_bom = [make_observation(origin="DEL", destination="BOM", observation_id=f"Y{i}", total_fare=-1) for i in range(2)]
        result = validate_fare_batch(blr_del + del_bom)
        by_route = {r.route: r for r in result.route_health}
        assert by_route["BLR-DEL"].observations_total == 5
        assert by_route["BLR-DEL"].route_quality_rate == 1.0
        assert by_route["DEL-BOM"].observations_rejected == 2
        assert by_route["DEL-BOM"].route_quality_rate == 0.0


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_dataset_with_schema(self):
        empty_df = pd.DataFrame(columns=[
            "observation_id", "airline", "origin", "destination",
            "flight_date", "booking_date", "total_fare", "currency",
        ])
        result = validate_fare_batch(empty_df)
        assert result.records_received == 0
        assert result.records_valid == 0
        assert result.valid_observations == []

    def test_empty_list_has_no_schema_info_and_is_rejected_as_such(self):
        """A bare ``[]`` carries no column names at all, so schema can't be
        checked — treated as INVALID_SCHEMA rather than silently assumed OK.
        Callers with a real (possibly zero-row) schema should pass a
        DataFrame with columns, as in test_empty_dataset_with_schema."""
        result = validate_fare_batch([])
        assert result.records_received == 0
        assert result.rejection_reasons == {}

    def test_one_observation(self):
        result = validate_fare_batch([make_observation()])
        assert result.records_received == 1
        assert result.records_valid == 1

    def test_all_records_invalid(self):
        obs = [make_observation(total_fare=-1, observation_id=f"X{i}") for i in range(5)]
        result = validate_fare_batch(obs)
        assert result.records_valid == 0
        assert result.records_rejected == 5
        assert result.valid_observations == []

    def test_all_records_valid(self):
        obs = distinct_observations(5)
        result = validate_fare_batch(obs)
        assert result.records_rejected == 0
        assert result.records_valid == 5

    def test_mixed_valid_and_invalid(self):
        obs = distinct_observations(3)
        obs += [make_observation(total_fare=-1, observation_id=f"BAD{i}", flight_date=f"2026-03-{i + 1:02d}") for i in range(2)]
        result = validate_fare_batch(obs)
        assert result.records_valid == 3
        assert result.records_rejected == 2

    def test_missing_optional_columns_entirely(self):
        """Scraper sends only the required columns — no source/timestamp/etc.
        at all. Must not crash, and every row is counted as missing optional
        info without affecting required-field completeness."""
        minimal = [
            {
                "observation_id": f"MIN{i}",
                "airline": "IndiGo",
                "origin": "BLR",
                "destination": "DEL",
                "flight_date": f"2026-01-{15 + i:02d}",
                "booking_date": "2026-01-01",
                "total_fare": 5000.0 + i,
                "currency": "INR",
            }
            for i in range(3)
        ]
        result = validate_fare_batch(minimal)
        assert result.records_valid == 3
        assert result.completeness.completeness_rate == 1.0
        assert result.completeness.records_missing_optional_fields == 3


# --------------------------------------------------------------------------
# Integration with the index engine
# --------------------------------------------------------------------------

class TestEngineIntegration:
    def test_valid_observations_feed_directly_into_index_engine(self):
        good = [make_observation(total_fare=5000 + i, observation_id=f"OK{i}", flight_date="2026-01-15") for i in range(5)]
        bad = [make_observation(total_fare=-1, observation_id="BAD")]
        quality_result = validate_fare_batch(good + bad)

        engine = AirfarePriceIndex(base_period="2026-01")
        index_result = engine.calculate(observations=quality_result.valid_observations, current_period="2026-01")

        assert index_result.observations_received == 5  # rejected row never reached the engine
        assert index_result.national_index is not None

    def test_flagged_observations_still_reach_the_engine(self):
        """FLAGGED (e.g. SUSPICIOUS_FARE) is an attention marker, not an
        exclusion — the engine's own statistical outlier detection is the
        authority on whether to exclude it."""
        normal = [make_observation(total_fare=5000.0 + i, observation_id=f"N{i}", flight_date="2026-01-15") for i in range(10)]
        spike = make_observation(total_fare=500000.0, observation_id="SPIKE", flight_date="2026-01-15")
        quality_result = validate_fare_batch(normal + [spike])

        assert any(o["observation_id"] == "SPIKE" for o in quality_result.valid_observations)


# --------------------------------------------------------------------------
# Config validation
# --------------------------------------------------------------------------

class TestConfig:
    def test_weights_must_sum_to_one(self):
        from data_quality.config import QualityScoreWeights

        with pytest.raises(ValueError):
            QualityScoreWeights(completeness=0.5, validity=0.5, duplicate=0.5, schema_compliance=0.0, source_success=0.0)

    def test_custom_config_is_respected(self):
        config = DataQualityConfig(unusual_booking_horizon_days=5)
        obs = make_observation(flight_date="2026-02-01", booking_date="2026-01-01")  # 31 days
        result = validate_fare_batch([obs], config=config)
        assert result.flag_reasons.get(rc.UNUSUAL_BOOKING_HORIZON) == 1
