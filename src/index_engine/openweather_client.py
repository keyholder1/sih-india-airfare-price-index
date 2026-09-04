"""Real HTTP client for OpenWeatherMap's Current Weather Data API
(https://openweathermap.org/current, endpoint /data/2.5/weather).

Unlike EONET, OpenWeatherMap genuinely requires a credential -- this
client reads it from the OPENWEATHER_API_KEY environment variable only
(never hard-coded, never logged, never included in any value this
module returns) per this project's security policy. A missing key
degrades this specific context source to unavailable; it never raises
into the caller and never blocks the index/analytics/dashboard.

NOTE ON VERIFICATION: this client is built against OpenWeatherMap's
long-stable, extensively documented public Current Weather Data
response contract. Unlike every other real integration added this
session (SerpApi, newsdata.io, NewsAPI.org, Event Registry, EONET --
each verified against a real live response before being written), this
one could NOT be live-verified in this session: the provided key
returned HTTP 401 at the time of writing, consistent with
OpenWeatherMap's own documented new-key activation delay (their FAQ
states new keys can take up to ~2 hours to activate), not necessarily
an invalid key. Treat the response parsing here as built-to-spec,
not live-confirmed, and verify with a real call once the key is active
(see tests/test_openweather_client.py for the exact fixture shape this
code expects).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

ENV_API_KEY = "OPENWEATHER_API_KEY"
ENV_BASE_URL = "OPENWEATHER_BASE_URL"
DEFAULT_BASE_URL = "https://api.openweathermap.org/data/2.5"
REQUEST_TIMEOUT_SECONDS = 10.0
#: Current conditions don't need re-fetching every second -- caching
#: avoids repeatedly requesting the same airport's weather (e.g. origin
#: and destination both looked up, then a second route sharing an
#: airport looked up moments later).
DEFAULT_CACHE_TTL_SECONDS = 600.0


@dataclass
class WeatherFetchResult:
    """Outcome of one OpenWeatherClient.get_current_weather() call.
    Never raises across this boundary -- same convention as
    EonetFetchResult / scraper.models.SourceCallResult."""

    status: str  # "SUCCESS" | "UNAVAILABLE" | "TIMEOUT" | "MALFORMED_RESPONSE" | "NOT_CONFIGURED"
    data: Optional[Dict[str, Any]] = field(default=None)
    error_detail: Optional[str] = None
    from_cache: bool = False


class OpenWeatherClient:
    """Thin, mockable wrapper over OpenWeatherMap's /weather endpoint.
    Never raises -- a missing key, network failure, timeout, or
    malformed response degrades to a WeatherFetchResult with a
    non-SUCCESS status."""

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
        self._cache: Dict[tuple, WeatherFetchResult] = {}
        self._cache_times: Dict[tuple, float] = {}

    def get_current_weather(self, latitude: float, longitude: float) -> WeatherFetchResult:
        """GET /weather?lat=..&lon=..&units=metric. Returns the raw
        parsed JSON body on success -- parsing into WeatherConditions
        happens one layer up (weather_context.py), same separation as
        EonetClient/eonet_context.py."""
        if not self._api_key:
            return WeatherFetchResult(status="NOT_CONFIGURED", error_detail=f"{ENV_API_KEY} is not set.")

        cache_key = (round(latitude, 4), round(longitude, 4))
        cached = self._cache.get(cache_key)
        if cached is not None and time.monotonic() - self._cache_times[cache_key] < self._cache_ttl:
            return WeatherFetchResult(status=cached.status, data=cached.data, error_detail=cached.error_detail, from_cache=True)

        params = {"lat": latitude, "lon": longitude, "units": "metric", "appid": self._api_key}
        try:
            client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
            response = client.get(f"{self._base_url}/weather", params=params)
        except httpx.TimeoutException:
            return WeatherFetchResult(status="TIMEOUT", error_detail="OpenWeatherMap request timed out.")
        except httpx.HTTPError as exc:
            return WeatherFetchResult(status="UNAVAILABLE", error_detail=f"OpenWeatherMap request failed: {exc}")
        finally:
            if self._client is None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

        if response.status_code == 401:
            return WeatherFetchResult(status="UNAVAILABLE", error_detail="OpenWeatherMap rejected the API key (HTTP 401).")
        if response.status_code == 429:
            return WeatherFetchResult(status="UNAVAILABLE", error_detail="OpenWeatherMap rate limit exceeded (HTTP 429).")
        if response.status_code != 200:
            return WeatherFetchResult(status="UNAVAILABLE", error_detail=f"OpenWeatherMap returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return WeatherFetchResult(status="MALFORMED_RESPONSE", error_detail=f"Could not parse OpenWeatherMap response as JSON: {exc}")

        if not isinstance(payload, dict) or "main" not in payload or "weather" not in payload:
            return WeatherFetchResult(status="MALFORMED_RESPONSE", error_detail="Response missing expected 'main'/'weather' fields.")

        result = WeatherFetchResult(status="SUCCESS", data=payload)
        self._cache[cache_key] = result
        self._cache_times[cache_key] = time.monotonic()
        return result
