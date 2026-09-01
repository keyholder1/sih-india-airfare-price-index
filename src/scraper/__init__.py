"""Airfare data collection layer — sits *before* the Data Quality module.

    from scraper import ScraperConfig, run_scrape
    from data_quality import validate_fare_batch
    from index_engine import AirfarePriceIndex

    raw_observations, report = run_scrape(ScraperConfig(mode="mock", tiers=(1,)))
    quality_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    engine = AirfarePriceIndex(base_period="2026-08")
    index_result = engine.calculate(quality_result.valid_observations, current_period="2026-08")

The scraper's job is COLLECTION only. It never validates, cleans, or
deduplicates — that is entirely ``data_quality``'s job (see
docs/scraper.md "Division of labour"). Every observation this module
produces conforms to docs/data_contract.md.

See docs/scraper.md for the full write-up: source evaluation, mock vs
live mode, provenance, and known limitations.
"""

from .config import ScraperConfig, ScraperMode
from .indigo_source import IndiGoCredentials, IndiGoSource, load_credentials_from_env
from .live_sources import EVALUATED_SOURCES, LIVE_SOURCES, SourceProfile, UnavailableLiveSource
from .mock_source import MockFareSource, default_mock_sources
from .models import RawFareObservation, ScrapeRunReport, SourceCallResult, SourceRunSummary
from .rate_limit import RateLimiter, RetryExhaustedError, retry_with_backoff
from .routes import RouteSpec, load_routes, route_pairs
from .runner import generate_booking_horizon_dates, run_scrape
from .source import FareSource, SearchRequest
from .storage import (
    build_collection_envelope,
    load_json_observations,
    write_collection_json,
    write_raw_run,
    write_run_report,
    write_validated_run,
)

__all__ = [
    "ScraperConfig",
    "ScraperMode",
    "run_scrape",
    "generate_booking_horizon_dates",
    "RouteSpec",
    "load_routes",
    "route_pairs",
    "FareSource",
    "SearchRequest",
    "RawFareObservation",
    "SourceCallResult",
    "SourceRunSummary",
    "ScrapeRunReport",
    "MockFareSource",
    "default_mock_sources",
    "SourceProfile",
    "UnavailableLiveSource",
    "EVALUATED_SOURCES",
    "LIVE_SOURCES",
    "RateLimiter",
    "retry_with_backoff",
    "RetryExhaustedError",
    "write_raw_run",
    "write_validated_run",
    "write_run_report",
    "write_collection_json",
    "build_collection_envelope",
    "load_json_observations",
    "IndiGoSource",
    "IndiGoCredentials",
    "load_credentials_from_env",
]

__version__ = "0.1.0"
