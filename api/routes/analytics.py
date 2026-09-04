"""
Analytics endpoints -- serve the engine's native output shapes for the
frontend dashboard's original contract (frontend/src/data/client.ts).

See api/services/analytics_service.py's module docstring for why these
return raw engine dicts instead of the api/schemas.py Pydantic models
the rest of this package uses.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from api.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("", summary="Full analytics result (price index, volatility, route inflation, rankings)")
def get_analytics() -> Dict[str, Any]:
    try:
        return analytics_service.get_analytics()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Analytics failed: {exc}")


@router.get("/timeseries", summary="Index time series, engine-native field names")
def get_timeseries(
    start_date: str = Query(..., pattern=r"^\d{4}-\d{2}$", examples=["2026-01"]),
    end_date: str = Query(..., pattern=r"^\d{4}-\d{2}$", examples=["2026-08"]),
) -> List[Dict[str, Any]]:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start_date ({start_date}) must not be after end_date ({end_date}).",
        )
    try:
        return analytics_service.get_timeseries(start_date, end_date)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeseries failed: {exc}")


@router.get("/routes/recommended", summary="DGCA-derived recommended route coverage")
def get_recommended_routes() -> Dict[str, Any]:
    try:
        return analytics_service.get_recommended_routes()
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recommended_routes.json not found.")


@router.get("/data-quality", summary="Full data quality report, engine-native field names")
def get_data_quality() -> Dict[str, Any]:
    try:
        return analytics_service.get_data_quality()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Data quality failed: {exc}")


@router.get("/forecast", summary="National baseline forecast + MoSPI CPI benchmark")
def get_forecast() -> Dict[str, Any]:
    try:
        return analytics_service.get_forecast()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Forecast failed: {exc}")


@router.get(
    "/events",
    summary="Recent real NASA EONET natural events associated with significant route movements",
)
def get_natural_events() -> Dict[str, Any]:
    """Never modifies or is consulted by the index calculation -- EONET
    is a read-only context layer (see docs/eonet_context.md). A failed
    EONET fetch is reported honestly via the response's own `status`
    field, not as a 500 -- this endpoint degrades to an empty/labelled
    result rather than erroring the dashboard."""
    try:
        return analytics_service.get_natural_events()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Natural events lookup failed: {exc}")
