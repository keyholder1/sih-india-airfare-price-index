"""Typed data structures for the OpenWeatherMap current-conditions
context layer.

Same style as news_models.py / eonet_models.py: plain dataclasses with a
to_dict(), no framework dependency, nothing imported by index.py or any
module that computes the price index. Weather is CURRENT conditions at
one airport, not a scored/ranked "event" like an EONET entry -- there is
no relevance scoring here, only "what are conditions like right now,"
shown for context alongside a route's fare movement, never claimed as
its cause. See docs/eonet_context.md's "Weather (OpenWeatherMap)"
section.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WeatherConditions:
    """Current weather at one airport/city, as returned by
    OpenWeatherMap's Current Weather Data API."""

    iata_code: str
    city_name: str
    observed_at: datetime
    temperature_c: float
    feels_like_c: float
    condition: str
    description: str
    wind_speed_ms: float
    humidity_pct: int
    visibility_m: Optional[int] = None
    is_mock: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["observed_at"] = self.observed_at.isoformat()
        return d


@dataclass
class RouteWeatherContext:
    """Current conditions at both ends of a route. Either side can be
    independently unavailable (e.g. one airport's coordinates aren't in
    CITY_COORDINATES, or the API call for it specifically failed) --
    never fabricated as "the same as the other side" or as a
    placeholder value."""

    route: str
    origin: Optional[WeatherConditions]
    destination: Optional[WeatherConditions]
    status: str  # "OK" | "PARTIAL" | "UNAVAILABLE"
    error_detail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "origin": self.origin.to_dict() if self.origin else None,
            "destination": self.destination.to_dict() if self.destination else None,
            "status": self.status,
            "error_detail": self.error_detail,
        }
