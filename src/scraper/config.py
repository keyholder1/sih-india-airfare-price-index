"""Scraper configuration.

Kept separate from ``index_engine.config`` and ``data_quality.config`` —
this module owns nothing about validation or index math, only "how should
the scraper behave" (which routes, how many retries, how fast).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

ScraperMode = Literal["mock", "live"]

DEFAULT_ROUTES_PATH = "data/routes/recommended_routes.json"


@dataclass
class ScraperConfig:
    """Configuration for one scrape run.

    Parameters
    ----------
    mode:
        ``"mock"`` uses :class:`scraper.mock_source.MockFareSource` —
        clearly-labelled fabricated data for development/demo. ``"live"``
        uses :data:`scraper.live_sources.LIVE_SOURCES` — see
        ``docs/scraper.md`` for why every entry there is currently
        ``SOURCE_UNAVAILABLE`` rather than actually scraping.
    tiers:
        Which tiers of ``data/routes/recommended_routes.json`` to collect
        for. ``(1,)`` (Tier 1 only, the top 20 routes by national traffic
        weight) is the default so a first run stays small and fast.
    routes_path:
        Path to the route list. Never hard-code routes in this package —
        this is the single source of truth (see :mod:`scraper.routes`).
    request_timeout_seconds, max_retries, backoff_base_seconds,
    backoff_max_seconds:
        Conservative per-request retry/backoff policy (see
        :mod:`scraper.rate_limit`). Defaults are deliberately gentle — this
        is not meant to be an aggressive crawler.
    min_interval_seconds:
        Minimum seconds between two requests to the *same* source
        (per-source rate limiting, see :class:`scraper.rate_limit.RateLimiter`).
    jitter_seconds:
        Random extra delay range added on top of ``min_interval_seconds``
        so requests don't land in a suspiciously regular pattern.
    max_concurrency:
        Upper bound on simultaneous in-flight requests across all
        sources/routes combined (``ThreadPoolExecutor(max_workers=...)``).
    passengers:
        Passenger count to request from every source.
    """

    mode: ScraperMode = "mock"
    tiers: Tuple[int, ...] = (1,)
    routes_path: str = DEFAULT_ROUTES_PATH
    request_timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 20.0
    min_interval_seconds: float = 1.0
    jitter_seconds: Tuple[float, float] = (0.0, 0.5)
    max_concurrency: int = 4
    passengers: int = 1
    output_dir: str = "data"

    def __post_init__(self) -> None:
        if not self.tiers:
            raise ValueError("tiers must be a non-empty tuple, e.g. (1,) for Tier 1 only")
        if any(t not in (1, 2, 3) for t in self.tiers):
            raise ValueError(f"tiers must be a subset of (1, 2, 3), got {self.tiers}")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
