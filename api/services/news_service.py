"""
Service adapter for the News / Event Context module.

Uses ``async`` because the real implementation may perform I/O-bound
work (e.g. fetching from an external news API).
"""

from __future__ import annotations

from src.engine.factory import get_news_context_engine
from api.schemas import (
    RouteContextResponse,
    NewsEventResponse,
    NaturalEventResponse,
    WeatherConditionsResponse,
)


async def get_route_context(route_code: str) -> RouteContextResponse:
    """Fetch contextual news/events/natural-events/weather for a route
    via the engine."""
    engine = get_news_context_engine()

    # The protocol method is async
    result = await engine.get_route_context(route_code)

    def _weather(w) -> WeatherConditionsResponse | None:
        if w is None:
            return None
        return WeatherConditionsResponse(
            iata_code=w.iata_code,
            city_name=w.city_name,
            observed_at=w.observed_at,
            temperature_c=w.temperature_c,
            feels_like_c=w.feels_like_c,
            condition=w.condition,
            description=w.description,
            wind_speed_ms=w.wind_speed_ms,
            humidity_pct=w.humidity_pct,
            visibility_m=w.visibility_m,
        )

    return RouteContextResponse(
        route=result.route,
        significant_movement=result.significant_movement,
        movement_direction=result.movement_direction,
        movement_pct=result.movement_pct,
        events=[
            NewsEventResponse(
                headline=ev.headline,
                source=ev.source,
                publication_date=ev.publication_date,
                url=ev.url,
                relevance_score=ev.relevance_score,
                data_source=ev.data_source,
            )
            for ev in result.events
        ],
        data_source=result.data_source,
        natural_events=[
            NaturalEventResponse(
                event_id=ne.event_id,
                title=ne.title,
                category=ne.category,
                category_label=ne.category_label,
                category_emoji=ne.category_emoji,
                event_date=ne.event_date,
                distance_from_origin_km=ne.distance_from_origin_km,
                distance_from_destination_km=ne.distance_from_destination_km,
                temporal_distance_days=ne.temporal_distance_days,
                relevance_score=ne.relevance_score,
                relevance_reason=ne.relevance_reason,
                source_url=ne.source_url,
                is_closed=ne.is_closed,
            )
            for ne in result.natural_events
        ],
        natural_events_status=result.natural_events_status,
        weather_origin=_weather(result.weather_origin),
        weather_destination=_weather(result.weather_destination),
        weather_status=result.weather_status,
    )
