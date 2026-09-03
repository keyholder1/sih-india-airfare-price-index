"""
Index endpoints — calculate and timeseries.

These endpoints may return **real or synthetic** data depending on
the engine implementation currently active (see ``src/engine/factory.py``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas import (
    IndexCalculateRequest,
    IndexCalculateResponse,
    TimeseriesResponse,
    ErrorResponse,
)
from api.services import index_service

router = APIRouter(prefix="/index", tags=["Index"])


@router.post(
    "/calculate",
    response_model=IndexCalculateResponse,
    summary="Calculate the airfare price index",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid observations or insufficient data."},
        422: {"model": ErrorResponse, "description": "Malformed request body."},
    },
)
def calculate_index(request: IndexCalculateRequest) -> IndexCalculateResponse:
    """
    Calculate the composite airfare price index from the provided
    observations, base period, and current period.

    Delegates all computation to the Index Engine — no math is
    performed in this layer.

    **Data provenance:** the ``data_source`` field in the response
    indicates whether the result was computed from real or synthetic
    (stub) data.
    """
    try:
        return index_service.calculate_index(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Index calculation failed: {exc}",
        )


@router.get(
    "/timeseries",
    response_model=TimeseriesResponse,
    summary="Retrieve index time series",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid date range."},
        422: {"model": ErrorResponse, "description": "Invalid query parameters."},
    },
)
def get_timeseries(
    start_date: str = Query(
        ...,
        description="Start of date range in YYYY-MM format.",
        pattern=r"^\d{4}-\d{2}$",
        examples=["2026-01"],
    ),
    end_date: str = Query(
        ...,
        description="End of date range in YYYY-MM format.",
        pattern=r"^\d{4}-\d{2}$",
        examples=["2026-08"],
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of periods to return per page. Default 100, max 500.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of periods to skip from the start of the range.",
    ),
) -> TimeseriesResponse:
    """
    Return index values (``period``, ``index``, ``MoM``, ``YoY``) for
    the requested date range, with pagination.

    **Page size:** defaults to 100 periods; maximum is 500.

    **Data provenance:** the ``data_source`` field in every point
    indicates real vs. synthetic.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start_date ({start_date}) must not be after end_date ({end_date}).",
        )

    try:
        return index_service.get_timeseries(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Timeseries retrieval failed: {exc}",
        )
