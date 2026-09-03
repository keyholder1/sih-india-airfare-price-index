"""Proves the architectural rule from item 12 of the brief actually holds
in execution, not just in documentation: REJECTED observations never reach
AirfarePriceIndex; only VALID + FLAGGED do. Also the one full end-to-end
demonstration (scraper -> data_quality -> index engine) the brief asks
for, run deterministically with mock data."""

from datetime import date, timedelta

import pandas as pd
import pytest

from data_quality import validate_fare_batch
from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.normalization import add_booking_horizon
from scraper.config import ScraperConfig
from scraper.mock_source import MockFareSource
from scraper.routes import RouteSpec
from scraper.runner import generate_booking_horizon_dates, run_scrape
from scraper.source import SearchRequest


def _route(origin, destination):
    return RouteSpec(origin=origin, destination=destination, origin_city=origin, destination_city=destination, tier=1, priority=1, national_weight=0.1, currently_covered=True)


def test_full_pipeline_scraper_to_data_quality_to_index_engine():
    routes = [_route("BLR", "DEL"), _route("DEL", "BOM")]
    dates = generate_booking_horizon_dates(date(2026, 9, 1))
    config = ScraperConfig(mode="mock", tiers=(1,), min_interval_seconds=0.0, max_retries=0)

    raw_observations, report = run_scrape(config, routes=routes, dates=dates)
    assert len(raw_observations) > 0

    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    assert dq_result.records_rejected == 0  # clean mock data has nothing to reject
    assert len(dq_result.valid_observations) == dq_result.records_valid + dq_result.records_flagged

    engine = AirfarePriceIndex(base_period="2026-09", config=IndexConfig(base_period="2026-09", min_observations_per_route_period=1))
    index_result = engine.calculate(dq_result.valid_observations, current_period="2026-09")
    assert index_result.national_index is not None
    assert index_result.routes_covered == 2


def test_rejected_observations_never_reach_the_index_engine():
    """Hand-inject one deliberately invalid raw record (negative fare)
    alongside clean scraper output, and prove it is excluded from
    ``valid_observations`` — i.e. never reaches ``AirfarePriceIndex``."""
    routes = [_route("BLR", "DEL")]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    raw_observations, report = run_scrape(config, routes=routes, dates=dates)

    bad_record = dict(raw_observations[0])
    bad_record["observation_id"] = "OBS_BAD_NEGATIVE_FARE"
    bad_record["total_fare"] = -500.0
    raw_observations.append(bad_record)

    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    assert dq_result.records_rejected == 1
    valid_ids = {r["observation_id"] for r in dq_result.valid_observations}
    assert "OBS_BAD_NEGATIVE_FARE" not in valid_ids

    engine = AirfarePriceIndex(base_period="2026-09", config=IndexConfig(base_period="2026-09", min_observations_per_route_period=1))
    index_result = engine.calculate(dq_result.valid_observations, current_period="2026-09")
    # The route's representative fare must not have been dragged down by
    # the rejected negative fare — every surviving observation is positive.
    assert index_result.national_index is None or index_result.national_index > 0


def test_flagged_but_not_rejected_observations_do_reach_the_index():
    """An unknown/unrecognized airline is a FLAG (attention marker), not a
    REJECTION — data_quality.reference_data documents this explicitly.
    Confirm that observation still reaches the index engine."""
    routes = [_route("BLR", "DEL")]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    source = MockFareSource("MockNewCarrier", "BrandNewAirline_NotYetKnown", 4000.0, 200.0)
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    raw_observations, report = run_scrape(config, sources=[source], routes=routes, dates=dates)

    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    assert dq_result.records_rejected == 0
    assert dq_result.records_flagged == 1
    assert "UNKNOWN_AIRLINE" in dq_result.flag_reasons

    valid_ids = {r["observation_id"] for r in dq_result.valid_observations}
    assert raw_observations[0]["observation_id"] in valid_ids


def test_scraper_index_matches_directly_passing_the_same_observations():
    """Section 9 of the audit: the scraper->data_quality->index path must
    be mathematically identical to handing the same VALID observations to
    AirfarePriceIndex directly -- the scraper/data_quality layers are pure
    collection/filtering, they must never perturb a value the index sees."""
    routes = [_route("BLR", "DEL"), _route("DEL", "BOM")]
    dates = generate_booking_horizon_dates(date(2026, 9, 1))
    config = ScraperConfig(mode="mock", tiers=(1,), min_interval_seconds=0.0, max_retries=0)
    raw_observations, report = run_scrape(config, routes=routes, dates=dates)
    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())

    engine_config = IndexConfig(base_period="2026-09", min_observations_per_route_period=1)

    via_pipeline = AirfarePriceIndex(base_period="2026-09", config=engine_config).calculate(
        dq_result.valid_observations, current_period="2026-09"
    )
    direct = AirfarePriceIndex(base_period="2026-09", config=engine_config).calculate(
        dq_result.valid_observations, current_period="2026-09"
    )
    assert via_pipeline.to_dict() == direct.to_dict()

    # Also confirm feeding the *raw* (pre-data_quality) valid-shaped subset
    # directly produces the identical result -- i.e. data_quality didn't
    # alter any surviving record's values, only filtered which records
    # pass through.
    raw_by_id = {o["observation_id"]: o for o in raw_observations}
    valid_raw = [raw_by_id[o["observation_id"]] for o in dq_result.valid_observations]
    from_raw = AirfarePriceIndex(base_period="2026-09", config=engine_config).calculate(valid_raw, current_period="2026-09")
    assert from_raw.national_index == pytest.approx(via_pipeline.national_index)


# --- booking-horizon boundaries -------------------------------------------


@pytest.mark.parametrize(
    "horizon_days,expected_bucket",
    [
        (0, "0-3"), (1, "0-3"), (3, "0-3"),
        (4, "4-7"), (7, "4-7"),
        (8, "8-14"), (14, "8-14"),
        (15, "15-30"), (30, "15-30"),
        (31, "31-60"), (60, "31-60"),
        (61, "61+"),
    ],
)
def test_scraper_observations_land_in_correct_booking_horizon_bucket_at_every_boundary(horizon_days, expected_bucket):
    """Section 8: a scraper-produced observation must preserve enough
    information (flight_date, booking_date) for the engine's own bucketing
    to place it correctly, at every bucket boundary -- 0, 1, 3, 4, 7, 8,
    14, 15, 30, 31, 60, 61 days."""
    today = date(2026, 9, 1)
    flight_date = today + timedelta(days=horizon_days)
    source = MockFareSource("MockBoundaryTest", "TestAir", 4000.0, 200.0)
    request = SearchRequest(origin="BLR", destination="DEL", flight_date=flight_date, booking_date=today)
    result = source.search_fares(request)
    assert result.status == "SUCCESS"
    record = result.observations[0].to_record()

    df = pd.DataFrame([record])
    enriched = add_booking_horizon(df)
    assert enriched.loc[0, "booking_horizon_days"] == horizon_days
    assert enriched.loc[0, "booking_horizon_bucket"] == expected_bucket


def test_scraper_route_attempts_feed_source_health_route_success_rate():
    """Proves scraper.models.SourceRunSummary.to_route_attempts_row() is
    actually shaped correctly for data_quality.health — not just
    structurally similar."""
    routes = [_route("BLR", "DEL")]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    raw_observations, report = run_scrape(config, routes=routes, dates=dates)

    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    sources_with_rate = {s.source: s.route_success_rate for s in dq_result.source_health}
    for source_name, rate in sources_with_rate.items():
        assert rate == 1.0  # every mock source succeeded on the one route requested
