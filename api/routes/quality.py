"""
Data quality endpoint.

May return **real or synthetic** data depending on the active engine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.schemas import QualityResponse, ErrorResponse
from api.services import quality_service

router = APIRouter(tags=["Quality"])


@router.get(
    "/quality",
    response_model=QualityResponse,
    summary="Get data quality report",
    responses={
        500: {"model": ErrorResponse, "description": "Internal error."},
    },
)
def get_quality() -> QualityResponse:
    """
    Return the latest data quality assessment including observations
    received, valid, rejected, flagged, rejection reasons, quality
    score, quality grade, route health, and source health.

    **Data provenance:** the ``data_source`` field indicates real
    vs. synthetic data.
    """
    try:
        return quality_service.assess_quality()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quality assessment failed: {exc}",
        )
