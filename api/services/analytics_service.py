"""
Service adapter for the frontend dashboard's analytics contract.

Unlike the other services in this package, these endpoints return the
*raw* engine dataclass output (``.to_dict()``) rather than reshaping it
through api/schemas.py's Pydantic models. That's deliberate: the frontend
(frontend/src/types/analytics.ts, dataQuality.ts, routes.ts) was built
directly against index_engine.AirfareAnalytics / data_quality's own
``to_dict()`` shapes and data/routes/recommended_routes.json's on-disk
shape -- see each type file's own header comment. Reshaping that into
IndexCalculateResponse-style schemas would just be a second, redundant
translation layer for the one client that already speaks the engine's
native contract.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd

import data_quality as data_quality_mod
from index_engine.analytics import AirfareAnalytics
from index_engine.utils import shift_period

from src.engine import data_access

_RECOMMENDED_ROUTES_PATH = data_access.REPO_ROOT / "data" / "routes" / "recommended_routes.json"


def _period_bounds(observations: List[Dict[str, Any]]) -> tuple[str, str]:
    periods = data_access.available_periods(observations)
    if not periods:
        raise ValueError("No periods available in the loaded observation set.")
    return periods[0], periods[-1]


def get_analytics() -> Dict[str, Any]:
    """Full AnalyticsResult.to_dict() -- national index, volatility,
    route inflation, rankings, route map objects, traffic coverage."""
    observations, _is_real = data_access.load_validated_observations()
    base_period, current_period = _period_bounds(observations)
    df = pd.DataFrame(observations)
    weights, weights_real = data_access.build_weights(observations)

    traffic_coverage = None
    if weights_real and "national_weight" in weights.columns:
        # Sum of national_weight over exactly the routes we actually cover
        # -- the same "what % of India's traffic do our routes represent"
        # figure docs/sih_pitch.md reports (e.g. the 8.8% example).
        traffic_coverage = round(float(weights["national_weight"].sum()), 4)

    engine = AirfareAnalytics(base_period=base_period, weights=weights if len(weights) else None)
    result = engine.calculate(observations=df, current_period=current_period)
    result.traffic_weight_coverage = traffic_coverage
    return result.to_dict()


def get_timeseries(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """One point per calendar month in [start_date, end_date], in the
    engine's own field names (national_index/mom_change_pct/yoy_change_pct)
    -- see frontend/src/types/analytics.ts's IndexTimeseriesPoint."""
    observations, _is_real = data_access.load_validated_observations()
    df = pd.DataFrame(observations)
    weights, _weights_real = data_access.build_weights(observations)
    data_periods = data_access.available_periods(observations)
    base_period = data_periods[0] if data_periods else start_date

    periods = []
    current = start_date
    for _ in range(1000):
        periods.append(current)
        if current >= end_date:
            break
        current = shift_period(current, 1)

    points = []
    for period in periods:
        try:
            from index_engine import AirfarePriceIndex

            result = AirfarePriceIndex(
                base_period=base_period, weights=weights if len(weights) else None
            ).calculate(observations=df, current_period=period)
            points.append(
                {
                    "period": period,
                    "national_index": result.national_index,
                    "mom_change_pct": result.mom_change_pct,
                    "yoy_change_pct": result.yoy_change_pct,
                }
            )
        except Exception:
            points.append({"period": period, "national_index": None, "mom_change_pct": None, "yoy_change_pct": None})
    return points


def get_recommended_routes() -> Dict[str, Any]:
    """Serves data/routes/recommended_routes.json as-is -- a real,
    already-computed artifact of route_selection.py, not recomputed here."""
    with open(_RECOMMENDED_ROUTES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_data_quality() -> Dict[str, Any]:
    """Full data_quality.DataQualityResult.to_dict() for whatever raw
    observations are on disk (see data_access.load_raw_observations)."""
    raw, _is_real = data_access.load_raw_observations()
    result = data_quality_mod.validate_fare_batch(raw)
    return result.to_dict()
