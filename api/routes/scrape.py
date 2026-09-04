"""On-demand two-route scrape endpoints: create a background job, poll it.

See api/services/scrape_job_service.py for the full pipeline this wraps
(real SerpApi call -> Data Quality -> Postgres -> re-run AirfareAnalytics).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.services import scrape_job_service

router = APIRouter(prefix="/scrape", tags=["On-demand scrape"])


class CreateScrapeJobRequest(BaseModel):
    origin: str = Field(..., description="3-letter IATA code, e.g. 'BLR'.", examples=["BLR"])
    destination: str = Field(..., description="3-letter IATA code, e.g. 'DEL'.", examples=["DEL"])


class CreateScrapeJobResponse(BaseModel):
    job_id: str


class ScrapeJobResponse(BaseModel):
    id: str
    origin: str
    destination: str
    status: str
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


@router.post(
    "/jobs",
    response_model=CreateScrapeJobResponse,
    summary="Trigger a real, live scrape for one origin/destination pair",
    responses={
        400: {"description": "Invalid route (not a 3-letter IATA code, or origin == destination)."},
        503: {"description": "Postgres is not configured -- see DATABASE_URL in .env.example."},
    },
)
async def create_scrape_job(request: CreateScrapeJobRequest) -> CreateScrapeJobResponse:
    """Kicks off the real scrape -> validate -> index pipeline in the
    background and returns immediately with a job id. This is a genuine
    live call to SerpApi/Google Flights -- it takes real time (roughly
    30s-2min for one route pair across all booking-horizon buckets) and
    consumes real API quota. Poll GET /scrape/jobs/{job_id} for progress.
    """
    try:
        job_id = await scrape_job_service.start_job(request.origin, request.destination)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return CreateScrapeJobResponse(job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=ScrapeJobResponse,
    summary="Poll the status of a scrape job",
    responses={404: {"description": "Unknown job id."}},
)
def get_scrape_job(job_id: str) -> ScrapeJobResponse:
    from src.engine import db

    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No job with id {job_id!r}.")
    return ScrapeJobResponse(**job)
