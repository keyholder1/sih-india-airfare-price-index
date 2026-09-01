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

# Load .env file if present
load_dotenv()

app = FastAPI(
    title="India Airfare Price Index API",
    description=(
        "Backend API for the India Airfare Price Index (SIH) project. "
        "Exposes the Index Engine and related modules to a frontend dashboard.\n\n"
        "**Note:** Until the real engine modules are integrated, all endpoints "
        "return synthetic stub data clearly labeled with `data_source: \"synthetic\"`."
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

app.include_router(v1_router)
