"""
Service adapter for the Data Quality module.
"""

from __future__ import annotations

from typing import Any

from src.engine.factory import get_quality_engine
from api.schemas import (
    QualityResponse,
    RouteHealthResponse,
    SourceHealthResponse,
)


def assess_quality(
    observations: list[dict[str, Any]] | None = None,
) -> QualityResponse:
    """Delegate quality assessment to the engine and shape the response."""
    engine = get_quality_engine()
    result = engine.assess_quality(observations or [])

    return QualityResponse(
        total_observations=result.total_observations,
        valid=result.valid,
        rejected=result.rejected,
        flagged=result.flagged,
        rejection_reasons=result.rejection_reasons,
        quality_score=result.quality_score,
        quality_grade=result.quality_grade,
        route_health=[
            RouteHealthResponse(
                route=rh.route,
                observations=rh.observations,
                valid=rh.valid,
                rejected=rh.rejected,
                flagged=rh.flagged,
                health_score=rh.health_score,
                status=rh.status,
            )
            for rh in result.route_health
        ],
        source_health=[
            SourceHealthResponse(
                source=sh.source,
                observations=sh.observations,
                valid=sh.valid,
                rejected=sh.rejected,
                reliability_score=sh.reliability_score,
            )
            for sh in result.source_health
        ],
        data_source=result.data_source,
    )
