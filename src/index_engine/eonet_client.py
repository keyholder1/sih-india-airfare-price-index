"""Real HTTP client for NASA EONET (Earth Observatory Natural Event
Tracker) v3 REST API -- https://eonet.gsfc.nasa.gov/api/v3.

VERIFIED LIVE (2026-09-04): EONET's public REST API is genuinely keyless
-- a plain GET with no auth header/param returns real event data
(confirmed against /api/v3/events and /api/v3/categories with no
credential of any kind). This module therefore does NOT require or send
any credential by default. Per this project's security policy (never
hard-code a secret; read it from an environment variable only, never
print/log it), EONET_API_KEY is still read from the environment and, if
set, threaded through as an `api_key` query parameter -- a harmless
no-op against the current API (which does not document or require it),
kept only for forward-compatibility should NASA ever gate these
endpoints. The key, if present, is never logged, never echoed in any
error message, and never included in any value this module returns.

This is a plain data-fetching client, deliberately isolated from
index_engine's statistical modules -- nothing here is imported by
index.py, aggregation.py, or any module that computes the price index.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

ENV_API_KEY = "EONET_API_KEY"
ENV_BASE_URL = "EONET_BASE_URL"
DEFAULT_BASE_URL = "https://eonet.gsfc.nasa.gov/api/v3"
REQUEST_TIMEOUT_SECONDS = 15.0
#: Natural events don't change second to second -- caching avoids
#: repeatedly requesting identical event data (e.g. two route lookups a
#: minute apart hitting the same India-wide query).
DEFAULT_CACHE_TTL_SECONDS = 900.0


@dataclass
class EonetFetchResult:
    """Outcome of one EonetClient.get_events() call. Never raises across
    this boundary -- a caller (eonet_context.py) checks `.status` instead
    of wrapping every call in a try/except, same convention as this
    project's scraper.models.SourceCallResult."""

    status: str  # "SUCCESS" | "UNAVAILABLE" | "TIMEOUT" | "MALFORMED_RESPONSE"
    events: List[Dict[str, Any]] = field(default_factory=list)
    error_detail: Optional[str] = None
    from_cache: bool = False


class EonetClient:
    """Thin, mockable wrapper over EONET's /events endpoint. Never
    raises -- a network failure, timeout, or malformed response degrades
    to an EonetFetchResult with a non-SUCCESS status, exactly like this
    project's real news providers (see newsdata_news_provider.py), so a
    caller's failure handling is uniform across every real external
    integration in this codebase.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._base_url = (base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get(ENV_API_KEY)
        self._client = client
        self._cache_ttl = cache_ttl_seconds
        self._cache: Dict[tuple, EonetFetchResult] = {}
        self._cache_times: Dict[tuple, float] = {}

    @staticmethod
    def _cache_key(params: Dict[str, Any]) -> tuple:
        return tuple(sorted(params.items()))

    def get_events(
        self,
        category: Optional[str] = None,
        bbox: Optional[str] = None,
        days: Optional[int] = None,
        status: str = "all",
        limit: Optional[int] = None,
    ) -> EonetFetchResult:
        """GET /events. ``bbox`` is EONET's own "minLon,minLat,maxLon,maxLat"
        format; ``category`` accepts a comma-separated list of category
        ids (verified live). Results are cached in-process per unique
        parameter combination for ``cache_ttl_seconds``."""
        params: Dict[str, Any] = {"status": status}
        if category:
            params["category"] = category
        if bbox:
            params["bbox"] = bbox
        if days:
            params["days"] = days
        if limit:
            params["limit"] = limit
        if self._api_key:
            params["api_key"] = self._api_key

        cache_key = self._cache_key(params)
        cached = self._cache.get(cache_key)
        if cached is not None and time.monotonic() - self._cache_times[cache_key] < self._cache_ttl:
            return EonetFetchResult(
                status=cached.status, events=cached.events, error_detail=cached.error_detail, from_cache=True
            )

        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.get(f"{self._base_url}/events", params=params)
        except httpx.TimeoutException:
            return EonetFetchResult(status="TIMEOUT", error_detail="EONET request timed out.")
        except httpx.HTTPError as exc:
            return EonetFetchResult(status="UNAVAILABLE", error_detail=f"EONET request failed: {exc}")
        finally:
            if self._client is None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        if response.status_code == 429:
            return EonetFetchResult(status="UNAVAILABLE", error_detail="EONET rate limit exceeded (HTTP 429).")
        if response.status_code != 200:
            return EonetFetchResult(status="UNAVAILABLE", error_detail=f"EONET returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return EonetFetchResult(status="MALFORMED_RESPONSE", error_detail=f"Could not parse EONET response as JSON: {exc}")

        if not isinstance(payload, dict):
            return EonetFetchResult(status="MALFORMED_RESPONSE", error_detail=f"Expected a JSON object, got {type(payload).__name__}.")
        events = payload.get("events")
        if not isinstance(events, list):
            return EonetFetchResult(status="MALFORMED_RESPONSE", error_detail="Expected 'events' to be a list.")

        result = EonetFetchResult(status="SUCCESS", events=events)
        self._cache[cache_key] = result
        self._cache_times[cache_key] = time.monotonic()
        return result
