"""
FastAPI application entry point.

Run with: ``uvicorn api.main:app --reload``
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import verify_api_key
from api.routes import (
    index_router,
    routes_router,
    quality_router,
    news_router,
    analytics_router,
    dashboard_router,
)
from api.routes.scrape import router as scrape_router
from api.forecasting_routes import router as forecasting_router
from src.engine import db

# Load .env file if present
load_dotenv()

# Idempotent: creates tables if they don't exist yet. A no-op (silently
# skipped, not fatal to app startup) if DATABASE_URL isn't set -- see
# db.is_configured() / data_access.py's flat-file fallback.
if db.is_configured():
    db.init_schema()

app = FastAPI(
    title="India Airfare Price Index API",
    description=(
        "Backend API for the India Airfare Price Index (SIH) project. "
        "Exposes the Index Engine and related modules to a frontend dashboard."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health check (no auth) ────────────────────────────────────────


@app.get("/health", tags=["Health"], summary="Health check")
def health_check() -> dict[str, str]:
    """Returns ``{"status": "ok"}`` if the server is running."""
    return {"status": "ok"}


# ── Versioned API router with auth ────────────────────────────────
# All /api/v1/ routes require a valid API key.

from fastapi import APIRouter

v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)],
)

v1_router.include_router(index_router)
v1_router.include_router(routes_router)
v1_router.include_router(quality_router)
v1_router.include_router(news_router)
v1_router.include_router(analytics_router)
v1_router.include_router(dashboard_router)
# Forecasting endpoints (national/route forecasts, baseline evaluation,
# CPI benchmark, booking-horizon analysis) -- see api/forecasting_routes.py.
v1_router.include_router(forecasting_router)
# On-demand two-route scrape -> validate -> index pipeline, backed by
# Postgres -- see api/services/scrape_job_service.py.
v1_router.include_router(scrape_router)

app.include_router(v1_router)
