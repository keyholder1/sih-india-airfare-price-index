"""
Dashboard summary endpoint.

Aggregates data from all engines into a single response.
May return **real or synthetic** data depending on the active engines.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.schemas import DashboardSummaryResponse, ErrorResponse
from api.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    summary="Get aggregated dashboard summary",
    responses={
        500: {"model": ErrorResponse, "description": "Internal error."},
    },
)
def get_dashboard_summary() -> DashboardSummaryResponse:
    """
    Return an aggregated dashboard summary including the current
    national index, MoM/YoY, route breakdowns, top movers,
    top contributors, data quality, coverage information, and alerts.

    **Data provenance:** the ``data_source`` field indicates real
    vs. synthetic data.
    """
    try:
        return dashboard_service.get_dashboard_summary()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dashboard summary failed: {exc}",
        )
