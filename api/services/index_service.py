"""
Service adapter for the Index Engine.

Translates between Pydantic request/response models and the engine's
Protocol interface. Contains NO math — all computation is delegated
to the engine.
"""

from __future__ import annotations

from dataclasses import asdict

from src.engine.factory import get_index_engine
from api.schemas import (
    IndexCalculateRequest,
    IndexCalculateResponse,
    RouteIndexResponse,
    TimeseriesPointResponse,
    TimeseriesResponse,
    PaginationMeta,
)

# Maximum page size for timeseries queries.
MAX_TIMESERIES_PAGE = 500
DEFAULT_TIMESERIES_PAGE = 100


def calculate_index(request: IndexCalculateRequest) -> IndexCalculateResponse:
    """Delegate index calculation to the engine and shape the response."""
    engine = get_index_engine()

    observations = [obs.model_dump() for obs in request.observations]
    result = engine.calculate_index(
        observations=observations,
        base_period=request.base_period,
        current_period=request.current_period,
        config=request.config,
    )

    return IndexCalculateResponse(
        national_index=result.national_index,
        mom=result.mom,
        yoy=result.yoy,
        base_period=result.base_period,
        current_period=result.current_period,
        route_indices=[
            RouteIndexResponse(
                route=ri.route,
                index=ri.index,
                mom=ri.mom,
                weight=ri.weight,
                contribution=ri.contribution,
                data_source=ri.data_source,
            )
            for ri in result.route_indices
        ],
        quality_score=result.quality_score,
        flags=result.flags,
        data_source=result.data_source,
        metadata=result.metadata,
    )


def get_timeseries(
    start_date: str,
    end_date: str,
    limit: int = DEFAULT_TIMESERIES_PAGE,
    offset: int = 0,
) -> TimeseriesResponse:
    """Retrieve time series from the engine with pagination."""
    engine = get_index_engine()

    # Clamp limit
    limit = max(1, min(limit, MAX_TIMESERIES_PAGE))
    offset = max(0, offset)

    all_points = engine.get_timeseries(start_date=start_date, end_date=end_date)
    total = len(all_points)
    page = all_points[offset : offset + limit]

    return TimeseriesResponse(
        data=[
            TimeseriesPointResponse(
                period=p.period,
                index=p.index,
                mom=p.mom,
                yoy=p.yoy,
                data_source=p.data_source,
            )
            for p in page
        ],
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
        data_source=page[0].data_source if page else "synthetic",
    )
