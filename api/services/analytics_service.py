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
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

import data_quality as data_quality_mod
from index_engine.analytics import AirfareAnalytics
from index_engine.mospi_income import default_mospi_income_path, load_mospi_income_series
from index_engine.utils import shift_period

from src.engine import data_access

_RECOMMENDED_ROUTES_PATH = data_access.REPO_ROOT / "data" / "routes" / "recommended_routes.json"
_MOSPI_CPI_PATH = data_access.REPO_ROOT / "data" / "benchmarks" / "cpi_1337.xlsx"
_MOSPI_INCOME_PATH = default_mospi_income_path(data_access.REPO_ROOT)


def _matrix_to_json(matrix: pd.DataFrame) -> Dict[str, Any]:
    """pandas DataFrame (NaN for "no data") -> JSON-safe nested lists
    (null for "no data", never 0 -- see route_analysis.inflation_matrix's
    own docstring: a route with no data is not a route with zero
    inflation)."""
    return {
        "origins": list(matrix.index),
        "destinations": list(matrix.columns),
        "values": [
            [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 2) for v in row]
            for row in matrix.values
        ],
    }


def _period_bounds(observations: List[Dict[str, Any]]) -> tuple[str, str]:
    periods = data_access.available_periods(observations)
    if not periods:
        raise ValueError("No periods available in the loaded observation set.")
    return periods[0], periods[-1]


def get_analytics() -> Dict[str, Any]:
    """Full AnalyticsResult.to_dict() -- national index, volatility,
    route inflation, rankings, route map objects, traffic coverage."""
    observations, provenance = data_access.load_validated_observations()
    base_period, current_period = _period_bounds(observations)
    df = pd.DataFrame(observations)
    weights, weights_real = data_access.build_weights(observations)

    traffic_coverage = None
    if weights_real and "national_weight" in weights.columns:
        # Sum of national_weight over exactly the routes we actually cover
        # -- the same "what % of India's traffic do our routes represent"
        # figure docs/sih_pitch.md reports (e.g. the 8.8% example).
        traffic_coverage = round(float(weights["national_weight"].sum()), 4)

    # Real MoSPI PLFS wage/earnings series, held flat across each real
    # value's calendar year -- see data/benchmarks/mospi_income_README.md.
    # Never fabricated: an empty/missing file yields an empty income
    # series, and calculate_affordability() reports DATA_UNAVAILABLE for
    # a period with no matching row rather than inventing one.
    income_series = load_mospi_income_series(_MOSPI_INCOME_PATH)

    engine = AirfareAnalytics(base_period=base_period, weights=weights if len(weights) else None)
    result = engine.calculate(
        observations=df,
        current_period=current_period,
        income_series=income_series if len(income_series) else None,
    )
    result.traffic_weight_coverage = traffic_coverage

    payload = result.to_dict()
    # Provenance of the observations behind this payload -- one of
    # data_access.PROVENANCE_REAL / _SYNTHETIC / _MIXED / _UNAVAILABLE.
    # A MIXED batch (some real, some mock observations) must never be
    # reported as REAL. The frontend must render its badge from this
    # field rather than guess it (see frontend/src/data/client.ts's
    # getDataStatus).
    payload["data_source"] = provenance
    # Not part of AnalyticsResult.to_dict() upstream -- inflation_matrix()
    # is a separate method on the result object (see index_engine.analytics
    # .AnalyticsResult / route_analysis.inflation_matrix). Attached here so
    # the one frontend that wants a heatmap doesn't need a second request.
    payload["inflation_matrix_mom"] = _matrix_to_json(result.inflation_matrix(metric="mom"))
    payload["inflation_matrix_yoy"] = _matrix_to_json(result.inflation_matrix(metric="yoy"))
    return payload


def get_timeseries(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """One point per calendar month in [start_date, end_date], in the
    engine's own field names (national_index/mom_change_pct/yoy_change_pct)
    -- see frontend/src/types/analytics.ts's IndexTimeseriesPoint."""
    observations, _provenance = data_access.load_validated_observations()
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
    raw, _provenance = data_access.load_raw_observations()
    result = data_quality_mod.validate_fare_batch(raw)
    return result.to_dict()


def get_forecast() -> Dict[str, Any]:
    """National baseline forecast (one period past the last real period)
    plus a MoSPI CPI benchmark comparison, if the reference file is
    present. Builds the forecasting dataset from the same on-disk
    observations get_analytics() uses -- see forecasting_routes.py for
    the same pattern against caller-supplied observations."""
    from forecasting import build_forecasting_dataset, compare_to_mospi_cpi, forecast_national_index, load_mospi_cpi_series

    observations, provenance = data_access.load_validated_observations()
    base_period, _current_period = _period_bounds(observations)
    df = pd.DataFrame(observations)
    weights, _weights_real = data_access.build_weights(observations)

    # Only a purely REAL batch may be forecast as non-synthetic -- a
    # MIXED or UNAVAILABLE batch is flagged synthetic too, same as the
    # provenance rule get_analytics() uses (never promote MIXED to real).
    is_synthetic = provenance != data_access.PROVENANCE_REAL

    dataset = build_forecasting_dataset(
        observations=df, base_period=base_period, weights=weights if len(weights) else None
    )
    forecast = forecast_national_index(dataset, is_synthetic_data=is_synthetic)

    cpi_benchmark: Optional[Dict[str, Any]] = None
    if _MOSPI_CPI_PATH.exists():
        mospi = load_mospi_cpi_series(_MOSPI_CPI_PATH)
        cpi_benchmark = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=is_synthetic).to_dict()
        # Never leak the local absolute filesystem path to a client.
        cpi_benchmark["mospi_source_file"] = str(_MOSPI_CPI_PATH.relative_to(data_access.REPO_ROOT))

    return {
        "national_forecast": forecast.to_dict(),
        "cpi_benchmark": cpi_benchmark,
        "data_source": provenance,
    }
