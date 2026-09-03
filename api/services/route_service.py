"""
Service adapter for the Route Analytics module.
"""

from __future__ import annotations

from src.engine.factory import get_route_analytics_engine
from api.schemas import RouteAnalysisResponse, RouteListResponse


def get_routes() -> RouteListResponse:
    """Retrieve route analysis from the engine and shape the response."""
    engine = get_route_analytics_engine()
    results = engine.get_route_analysis()

    route_responses = [
        RouteAnalysisResponse(
            route=ra.route,
            route_index=ra.route_index,
            mom=ra.mom,
            weight=ra.weight,
            contribution=ra.contribution,
            traffic_coverage=ra.traffic_coverage,
            status=ra.status,
            data_source=ra.data_source,
        )
        for ra in results
    ]

    return RouteListResponse(
        routes=route_responses,
        data_source=route_responses[0].data_source if route_responses else "synthetic",
    )
