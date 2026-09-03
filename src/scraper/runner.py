"""Orchestrates a scrape run: routes x dates x sources -> raw observations
+ a structured :class:`~scraper.models.ScrapeRunReport`.

This is the only module that knows about concurrency, retries, and rate
limiting — every :class:`~scraper.source.FareSource` implementation stays
simple (just "given a request, return a result").
"""

from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from index_engine.config import BOOKING_HORIZON_BUCKETS

from .config import ScraperConfig
from .live_sources import LIVE_SOURCES
from .mock_source import default_mock_sources
from .models import RawFareObservation, ScrapeRunReport, SourceCallResult, SourceRunSummary
from .rate_limit import RateLimiter, RetryExhaustedError, retry_with_backoff
from .routes import RouteSpec, load_routes
from .source import FareSource, SearchRequest

logger = logging.getLogger("scraper")
if not logger.handlers:
    # A library-friendly default: emit somewhere visible in scripts/tests
    # without forcing every caller to configure logging first.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


def generate_booking_horizon_dates(today: date) -> List[Tuple[date, date]]:
    """One (flight_date, booking_date) pair per bucket in
    ``index_engine.config.BOOKING_HORIZON_BUCKETS`` — never hard-codes the
    horizon boundaries itself (item 17 of the brief), just samples one
    representative flight date inside each bucket the engine already
    defines. ``booking_date`` is always ``today`` — a single run collects
    "what does it cost to book each of these horizons right now."
    """
    pairs: List[Tuple[date, date]] = []
    for _label, lower, upper in BOOKING_HORIZON_BUCKETS:
        sample_offset = lower if upper is None else (lower + upper) // 2
        sample_offset = max(sample_offset, 1)  # never sample same-day as booking_date=today
        flight_date = today.fromordinal(today.toordinal() + sample_offset)
        pairs.append((flight_date, today))
    return pairs


def _run_id(now: datetime) -> str:
    return f"run_{now.strftime('%Y%m%dT%H%M%SZ')}"


def _classify_exception(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "TIMEOUT"
    if "rate" in name or "429" in str(exc):
        return "RATE_LIMITED"
    if "http" in name or "connection" in name:
        return "HTTP_ERROR"
    return "PARSE_ERROR"


#: Statuses worth retrying: transient conditions where asking again
#: shortly is reasonable. Deliberately excludes EMPTY_RESULT (the source
#: answered normally and just has nothing -- not a failure),
#: SOURCE_UNAVAILABLE (a deliberate, permanent "cannot use this source"
#: marker -- retrying would mean hammering a source we've already decided
#: not to access), and PARSE_ERROR/MALFORMED_RESPONSE (more likely our own
#: parsing bug than a transient server issue -- retrying identical input
#: through identical code won't produce a different result).
_RETRYABLE_STATUSES = frozenset({"TIMEOUT", "HTTP_ERROR", "RATE_LIMITED"})


class _RetryableSourceStatus(Exception):
    """Internal-only signal that bridges a *returned* transient-failure
    ``SourceCallResult`` into :func:`retry_with_backoff`, which only reacts
    to raised exceptions. ``FareSource.search_fares`` is documented to
    encode ordinary failures as a status rather than raise (see
    ``source.py``) -- without this bridge, retry_with_backoff could only
    ever retry a source that violates its own documented contract by
    raising, which meant the shipped ``MockFareSource`` (which never
    raises) could never be retried at all, and neither could any future
    source implemented per the documented interface. Never escapes
    :func:`_call_source`."""

    def __init__(self, result: SourceCallResult) -> None:
        super().__init__(result.status)
        self.result = result


def _call_source(
    source: FareSource,
    request: SearchRequest,
    limiter: RateLimiter,
    config: ScraperConfig,
) -> SourceCallResult:
    def attempt() -> SourceCallResult:
        # Rate-limit every attempt, not just the first -- a retry is still
        # a real call to the source and must respect the same minimum
        # interval.
        limiter.wait()
        result = source.search_fares(request)
        if result.status in _RETRYABLE_STATUSES:
            raise _RetryableSourceStatus(result)
        return result

    try:
        return retry_with_backoff(
            attempt,
            max_retries=config.max_retries,
            backoff_base_seconds=config.backoff_base_seconds,
            backoff_max_seconds=config.backoff_max_seconds,
            source_name=source.name,
        )
    except RetryExhaustedError as exc:
        underlying = exc.__cause__ if exc.__cause__ is not None else exc
        if isinstance(underlying, _RetryableSourceStatus):
            # Preserve the source's own last-attempt status/error_detail
            # rather than re-deriving one from the exception type.
            return underlying.result
        status = _classify_exception(underlying) if isinstance(underlying, Exception) else "PARSE_ERROR"
        return SourceCallResult(status=status, observations=[], error_detail=str(underlying))


def _stamp_provenance(observation: RawFareObservation, run_id: str, scraped_at: str) -> RawFareObservation:
    updates = {}
    if observation.run_id is None:
        updates["run_id"] = run_id
    if observation.scraped_at is None:
        updates["scraped_at"] = scraped_at
    return dataclasses.replace(observation, **updates) if updates else observation


def run_scrape(
    config: Optional[ScraperConfig] = None,
    sources: Optional[List[FareSource]] = None,
    routes: Optional[List[RouteSpec]] = None,
    dates: Optional[List[Tuple[date, date]]] = None,
    today: Optional[date] = None,
) -> Tuple[List[dict], ScrapeRunReport]:
    """Run one scrape and return ``(raw_observations, report)``.

    ``raw_observations`` is a list of plain dicts (via
    ``RawFareObservation.to_record()``) — ready to hand straight to
    ``data_quality.validate_fare_batch`` and, after that, to
    ``AirfarePriceIndex.calculate``. This function never validates or
    cleans anything itself (see docs/scraper.md "Division of labour").
    """
    config = config or ScraperConfig()
    today = today or date.today()
    started_at = datetime.now(timezone.utc)
    run_id = _run_id(started_at)

    routes = routes if routes is not None else load_routes(config.routes_path, tiers=config.tiers)
    dates = dates if dates is not None else generate_booking_horizon_dates(today)
    if sources is None:
        sources = default_mock_sources() if config.mode == "mock" else list(LIVE_SOURCES)

    logger.info("[INFO] Starting scrape run %s (mode=%s, routes=%d, dates=%d, sources=%d)", run_id, config.mode, len(routes), len(dates), len(sources))

    limiters: Dict[str, RateLimiter] = {
        s.name: RateLimiter(config.min_interval_seconds, config.jitter_seconds) for s in sources
    }

    tasks = [
        (source, route, flight_date, booking_date)
        for source in sources
        for route in routes
        for flight_date, booking_date in dates
    ]

    observations: List[RawFareObservation] = []
    per_source_route_status: Dict[str, Dict[str, bool]] = {s.name: {} for s in sources}
    per_source_failures: Dict[str, Dict[str, int]] = {s.name: {} for s in sources}
    per_source_observations: Dict[str, int] = {s.name: 0 for s in sources}
    overall_failure_reasons: Dict[str, int] = {}

    def worker(task):
        source, route, flight_date, booking_date = task
        request = SearchRequest(origin=route.origin, destination=route.destination, flight_date=flight_date, booking_date=booking_date, passengers=config.passengers)
        result = _call_source(source, request, limiters[source.name], config)
        return source, route, result

    with ThreadPoolExecutor(max_workers=config.max_concurrency) as pool:
        futures = [pool.submit(worker, task) for task in tasks]
        for future in as_completed(futures):
            source, route, result = future.result()
            route_key = route.route
            success = result.status == "SUCCESS"
            per_source_route_status[source.name].setdefault(route_key, False)
            per_source_route_status[source.name][route_key] = per_source_route_status[source.name][route_key] or success

            if success:
                logger.info("[INFO] Route %s | Source: %s | %d fare(s) collected", route_key, source.name, len(result.observations))
                per_source_observations[source.name] += len(result.observations)
                observations.extend(result.observations)
            else:
                logger.warning("[WARN] Route %s | Source: %s | %s%s", route_key, source.name, result.status, f" ({result.error_detail})" if result.error_detail else "")
                per_source_failures[source.name][result.status] = per_source_failures[source.name].get(result.status, 0) + 1
                overall_failure_reasons[result.status] = overall_failure_reasons.get(result.status, 0) + 1

    scraped_at = datetime.now(timezone.utc).isoformat()
    observations = [_stamp_provenance(o, run_id, scraped_at) for o in observations]

    source_summaries: List[SourceRunSummary] = []
    for source in sources:
        route_statuses = per_source_route_status[source.name]
        routes_attempted = sorted(route_statuses.keys())
        routes_successful = sum(1 for ok in route_statuses.values() if ok)
        source_summaries.append(
            SourceRunSummary(
                source=source.name,
                routes_requested=len(routes_attempted),
                routes_successful=routes_successful,
                routes_failed=len(routes_attempted) - routes_successful,
                routes_attempted=routes_attempted,
                observations_collected=per_source_observations[source.name],
                failure_breakdown=per_source_failures[source.name],
            )
        )

    routes_successful_overall = sum(
        1 for route in routes if any(per_source_route_status[s.name].get(route.route, False) for s in sources)
    )

    finished_at = datetime.now(timezone.utc)
    report = ScrapeRunReport(
        run_id=run_id,
        mode=config.mode,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        routes_requested=len(routes),
        routes_successful=routes_successful_overall,
        routes_failed=len(routes) - routes_successful_overall,
        observations_collected=len(observations),
        source_summaries=source_summaries,
        failure_reasons=overall_failure_reasons,
    )
    logger.info("[INFO] Run completed: %d observation(s) from %d/%d route(s)", len(observations), routes_successful_overall, len(routes))

    return [o.to_record() for o in observations], report
