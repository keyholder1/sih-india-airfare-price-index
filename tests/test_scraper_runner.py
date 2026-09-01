import time
from datetime import date, timedelta

import pytest

from index_engine.config import BOOKING_HORIZON_BUCKETS
from scraper.config import ScraperConfig
from scraper.mock_source import MockFareSource, default_mock_sources
from scraper.models import SourceCallResult
from scraper.rate_limit import RateLimiter
from scraper.routes import RouteSpec
from scraper.runner import generate_booking_horizon_dates, run_scrape
from scraper.source import FareSource, SearchRequest


def _route(origin="BLR", destination="DEL", tier=1):
    return RouteSpec(origin=origin, destination=destination, origin_city=origin, destination_city=destination, tier=tier, priority=1, national_weight=0.1, currently_covered=True)


# --- booking horizon sampling -------------------------------------------


def test_generate_booking_horizon_dates_has_one_pair_per_bucket():
    dates = generate_booking_horizon_dates(date(2026, 9, 1))
    assert len(dates) == len(BOOKING_HORIZON_BUCKETS)


def test_generate_booking_horizon_dates_falls_within_each_bucket_range():
    today = date(2026, 9, 1)
    dates = generate_booking_horizon_dates(today)
    for (flight_date, booking_date), (_label, lower, upper) in zip(dates, BOOKING_HORIZON_BUCKETS):
        horizon = (flight_date - booking_date).days
        assert horizon >= lower
        if upper is not None:
            assert horizon <= upper
        assert booking_date == today


# --- multi-source, graceful failure, retries ----------------------------


def test_run_scrape_mock_mode_collects_from_every_configured_source():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    obs, report = run_scrape(config, routes=routes, dates=dates)
    assert len(obs) == len(default_mock_sources())
    assert report.routes_requested == 1
    assert report.routes_successful == 1
    assert {o["source"] for o in obs} == {s.name for s in default_mock_sources()}


class _AlwaysFailsSource(FareSource):
    name = "AlwaysFails"

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        raise TimeoutError("simulated timeout")


def test_a_failing_source_does_not_crash_the_whole_run_and_is_recorded():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    obs, report = run_scrape(config, sources=[_AlwaysFailsSource()], routes=routes, dates=dates)
    assert obs == []
    assert report.routes_successful == 0
    assert report.routes_failed == 1
    assert report.failure_reasons.get("TIMEOUT") == 1
    summary = report.source_summaries[0]
    assert summary.failure_breakdown.get("TIMEOUT") == 1


class _FlakyThenSucceedsSource(FareSource):
    """Fails the first two calls, succeeds on the third — exercises the
    retry/backoff path without a real network dependency."""

    name = "Flaky"

    def __init__(self) -> None:
        self.attempts = 0

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        self.attempts += 1
        if self.attempts < 3:
            raise ConnectionError("simulated transient failure")
        return SourceCallResult(status="SUCCESS", observations=MockFareSource("Flaky", "TestAir", 4000.0, 500.0).search_fares(request).observations)


def test_retry_with_backoff_eventually_succeeds_after_transient_failures():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=3, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    source = _FlakyThenSucceedsSource()
    obs, report = run_scrape(config, sources=[source], routes=routes, dates=dates)
    assert len(obs) == 1
    assert report.routes_successful == 1
    assert source.attempts == 3


def test_retries_exhausted_is_recorded_as_a_failure_not_a_crash():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=1, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    obs, report = run_scrape(config, sources=[_AlwaysFailsSource()], routes=routes, dates=dates)
    assert obs == []
    assert report.routes_failed == 1


class _FlakyStatusThenSucceedsSource(FareSource):
    """Fails via a normal *returned* SourceCallResult status (the
    documented FareSource contract -- see source.py) rather than raising,
    for the first two calls, then succeeds. retry_with_backoff only reacts
    to raised exceptions, so without _call_source bridging a retryable
    status into that loop, this source would never be retried at all."""

    name = "FlakyStatus"

    def __init__(self) -> None:
        self.attempts = 0

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        self.attempts += 1
        if self.attempts < 3:
            return SourceCallResult(status="TIMEOUT", observations=[], error_detail="simulated timeout status")
        return SourceCallResult(status="SUCCESS", observations=MockFareSource("FlakyStatus", "TestAir", 4000.0, 500.0).search_fares(request).observations)


def test_transient_status_returned_not_raised_is_still_retried():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=3, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    source = _FlakyStatusThenSucceedsSource()
    obs, report = run_scrape(config, sources=[source], routes=routes, dates=dates)
    assert len(obs) == 1
    assert report.routes_successful == 1
    assert source.attempts == 3


class _AlwaysReturnsSourceUnavailable(FareSource):
    """SOURCE_UNAVAILABLE is a deliberate, permanent marker (robots.txt
    disallowed, needs credentials we don't have, etc.) -- retrying it would
    mean hammering a source we've already decided not to access, so it
    must NOT be retried."""

    name = "PermanentlyUnavailable"

    def __init__(self) -> None:
        self.attempts = 0

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        self.attempts += 1
        return SourceCallResult(status="SOURCE_UNAVAILABLE", observations=[], error_detail="robots.txt disallows")


def test_source_unavailable_status_is_not_retried():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=3, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    source = _AlwaysReturnsSourceUnavailable()
    obs, report = run_scrape(config, sources=[source], routes=routes, dates=dates)
    assert obs == []
    assert source.attempts == 1  # single attempt, never retried
    assert report.failure_reasons.get("SOURCE_UNAVAILABLE") == 1


class _AlwaysReturnsMalformedResponse(FareSource):
    """A source's response that parsed but doesn't make sense (wrong
    shape, missing fields the source normally has) -- more likely a bug in
    our own parsing than a transient server hiccup, so (like
    SOURCE_UNAVAILABLE) this must not be retried."""

    name = "MalformedSource"

    def __init__(self) -> None:
        self.attempts = 0

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        self.attempts += 1
        return SourceCallResult(status="MALFORMED_RESPONSE", observations=[], error_detail="unexpected response shape")


def test_malformed_response_is_recorded_and_not_retried():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=3, backoff_base_seconds=0.01, backoff_max_seconds=0.02)
    source = _AlwaysReturnsMalformedResponse()
    obs, report = run_scrape(config, sources=[source], routes=routes, dates=dates)
    assert obs == []
    assert source.attempts == 1
    assert report.failure_reasons.get("MALFORMED_RESPONSE") == 1


class _EmptyResultSource(FareSource):
    name = "EmptySource"

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        return SourceCallResult(status="EMPTY_RESULT", observations=[])


def test_empty_result_is_tracked_distinctly_from_a_hard_failure():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    obs, report = run_scrape(config, sources=[_EmptyResultSource()], routes=routes, dates=dates)
    assert obs == []
    assert report.failure_reasons.get("EMPTY_RESULT") == 1


def test_route_success_when_at_least_one_source_succeeds_even_if_others_fail():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    good = MockFareSource("Good", "TestAir", 4000.0, 500.0)
    obs, report = run_scrape(config, sources=[good, _AlwaysFailsSource()], routes=routes, dates=dates)
    assert len(obs) == 1
    assert report.routes_successful == 1  # route counts as successful overall
    good_summary = next(s for s in report.source_summaries if s.source == "Good")
    bad_summary = next(s for s in report.source_summaries if s.source == "AlwaysFails")
    assert good_summary.routes_successful == 1
    assert bad_summary.routes_failed == 1


def test_route_wide_failure_when_every_source_fails():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    obs, report = run_scrape(config, sources=[_AlwaysFailsSource()], routes=routes, dates=dates)
    assert report.routes_failed == 1
    assert report.routes_successful == 0


# --- provenance -----------------------------------------------------------


def test_provenance_fields_are_stamped_by_the_runner():
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    obs, report = run_scrape(config, routes=routes, dates=dates)
    for o in obs:
        assert o["run_id"] == report.run_id
        assert o["scraped_at"] is not None
        assert o["is_mock"] is True


def test_duplicate_observations_are_not_removed_by_the_scraper():
    """Item 7: the scraper must not aggressively dedupe — that is
    data_quality's job. Same route/date collected from two sources should
    both survive, even though they might later be flagged as
    POTENTIAL_DUPLICATE by data_quality if their fares happen to be close."""
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    obs, _ = run_scrape(config, routes=routes, dates=dates)
    # 3 default mock sources, none removed
    assert len(obs) == 3
    assert len({o["observation_id"] for o in obs}) == 3


def test_the_same_source_asked_twice_for_the_identical_route_and_date_is_not_collapsed():
    """Even a literal duplicate task (same source/route/flight_date/
    booking_date, which necessarily produces the identical deterministic
    observation_id) must survive as two rows — collapsing on
    observation_id is exactly the aggressive scraper-side dedup item 7
    forbids. data_quality.duplicates is where that decision belongs."""
    routes = [_route()]
    dates = [(date(2026, 9, 15), date(2026, 9, 1)), (date(2026, 9, 15), date(2026, 9, 1))]
    config = ScraperConfig(mode="mock", min_interval_seconds=0.0, max_retries=0)
    source = MockFareSource("MockIndiGo", "IndiGo", 4200.0, 900.0)
    obs, _ = run_scrape(config, sources=[source], routes=routes, dates=dates)
    assert len(obs) == 2
    assert obs[0]["observation_id"] == obs[1]["observation_id"]


# --- rate limiting ----------------------------------------------------------


def test_rate_limiter_enforces_minimum_interval_between_calls():
    limiter = RateLimiter(min_interval_seconds=0.3)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    elapsed = time.monotonic() - start
    # Generous tolerance: OS sleep timers (esp. Windows' default ~15ms
    # resolution) can undershoot a short requested delay slightly.
    assert elapsed >= 0.25


def test_rate_limiter_zero_interval_does_not_block():
    limiter = RateLimiter(min_interval_seconds=0.0)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - start < 0.1
