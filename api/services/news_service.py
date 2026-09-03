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
)


async def get_route_context(route_code: str) -> RouteContextResponse:
    """Fetch contextual news/events for a route via the engine."""
    engine = get_news_context_engine()

    # The protocol method is async
    result = await engine.get_route_context(route_code)

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
    )
