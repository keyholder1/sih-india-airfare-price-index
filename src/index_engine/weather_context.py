"""Current-conditions context layer (OpenWeatherMap) -- answers "what
are conditions like right now at this route's two airports?" A live
snapshot, not a scored/ranked history like EONET: weather is always
"there," so there is nothing to rank against a time window. Shown
purely for context alongside a route's fare movement -- never claimed
as its cause (same discipline as news_context.py / eonet_context.py).

Optional and additive. Nothing here is imported by index.py or
aggregation.py, and nothing here mutates an IndexResult or any other
index output. See docs/eonet_context.md's "Weather (OpenWeatherMap)"
section, including exactly what happens when OpenWeatherMap is
unavailable or unconfigured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .geo_metadata import CITY_COORDINATES
from .openweather_client import OpenWeatherClient, WeatherFetchResult
from .weather_models import RouteWeatherContext, WeatherConditions


def _parse_conditions(iata_code: str, payload: dict) -> Optional[WeatherConditions]:
    try:
        main = payload["main"]
        weather = payload["weather"][0]
        wind = payload.get("wind") or {}
        return WeatherConditions(
            iata_code=iata_code,
            city_name=payload.get("name") or iata_code,
            observed_at=datetime.fromtimestamp(payload["dt"], tz=timezone.utc) if payload.get("dt") else datetime.now(timezone.utc),
            temperature_c=float(main["temp"]),
            feels_like_c=float(main.get("feels_like", main["temp"])),
            condition=weather.get("main", "Unknown"),
            description=weather.get("description", ""),
            wind_speed_ms=float(wind.get("speed", 0.0)),
            humidity_pct=int(main.get("humidity", 0)),
            visibility_m=payload.get("visibility"),
            is_mock=False,
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None


class WeatherContextService:
    """Wires an OpenWeatherClient to CITY_COORDINATES. Never raises --
    a failure for one or both airports degrades this service's own
    result, it must never propagate up and break the
    index/analytics/dashboard."""

    def __init__(self, client: Optional[OpenWeatherClient] = None) -> None:
        self.client = client or OpenWeatherClient()

    def _fetch_one(self, iata_code: str) -> tuple[Optional[WeatherConditions], Optional[str]]:
        coord = CITY_COORDINATES.get(iata_code.upper())
        if coord is None:
            return None, f"No known coordinates for {iata_code} (index_engine.geo_metadata.CITY_COORDINATES)."
        try:
            fetch: WeatherFetchResult = self.client.get_current_weather(coord[0], coord[1])
        except Exception as exc:  # noqa: BLE001 -- weather must never take the pipeline down with it
            return None, f"{type(exc).__name__}: {exc}"
        if fetch.status != "SUCCESS" or fetch.data is None:
            return None, fetch.error_detail
        parsed = _parse_conditions(iata_code, fetch.data)
        if parsed is None:
            return None, f"Could not parse OpenWeatherMap response for {iata_code}."
        return parsed, None

    def get_route_weather(self, origin: str, destination: str) -> RouteWeatherContext:
        origin_conditions, origin_error = self._fetch_one(origin)
        dest_conditions, dest_error = self._fetch_one(destination)

        if origin_conditions is not None and dest_conditions is not None:
            status = "OK"
        elif origin_conditions is not None or dest_conditions is not None:
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"

        error_detail = " | ".join(e for e in (origin_error, dest_error) if e) or None

        return RouteWeatherContext(
            route=f"{origin}-{destination}",
            origin=origin_conditions,
            destination=dest_conditions,
            status=status,
            error_detail=error_detail if status != "OK" else None,
        )
