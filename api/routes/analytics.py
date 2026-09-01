"""
Analytics endpoints — placeholder for future volatility, trend,
and advanced analytics features.

Currently ships with no endpoints. Add routes here as the analytics
modules are developed.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Future endpoints:
# - GET /api/v1/analytics/volatility
# - GET /api/v1/analytics/trends
# - GET /api/v1/analytics/seasonal
