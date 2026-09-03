"""
News / event context endpoint.

May return **real or synthetic** data depending on the active engine.

News is contextual only — it never modifies the index.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from api.schemas import RouteContextResponse, ErrorResponse
from api.services import news_service

router = APIRouter(tags=["News / Context"])


@router.get(
    "/routes/{route}/context",
    response_model=RouteContextResponse,
    summary="Get news/event context for a route",
    responses={
        404: {"model": ErrorResponse, "description": "Unknown route."},
        500: {"model": ErrorResponse, "description": "Internal error."},
    },
)
async def get_route_context(
    route: str = Path(
        ...,
        description="IATA route code, e.g. 'DEL-BOM'.",
        examples=["DEL-BOM"],
    ),
) -> RouteContextResponse:
    """
    Fetch contextual news and events for the specified route.

    This endpoint uses ``async`` because the underlying engine may
    perform I/O-bound work (e.g. fetching from an external news API).

    **News is contextual only — it never modifies the index.**

    **Data provenance:** the ``data_source`` field indicates real
    vs. synthetic data.
    """
    try:
        return await news_service.get_route_context(route)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"News/context retrieval failed: {exc}",
        )
