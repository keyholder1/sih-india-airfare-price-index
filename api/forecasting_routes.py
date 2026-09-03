"""FastAPI routes for the forecasting module.

Thin HTTP wrapper, same philosophy as ``api/main.py``: every route below
only translates JSON <-> the ``forecasting`` package's plain Python
functions/dataclasses. No forecasting, backtesting, index-aggregation, or
booking-horizon-partitioning logic is duplicated here -- each handler
calls straight into ``forecasting.*`` and returns ``result.to_dict()``
(or an equivalent direct field mapping for dataclasses without one),
exactly like ``api/main.py``'s existing ``/index/*`` routes do for
``index_engine``.

Included into the main app via ``app.include_router(router)`` in
``api/main.py`` -- kept in its own module (rather than appended to
``main.py``) purely to keep the two concerns (index-engine HTTP wrapper
vs. forecasting HTTP wrapper) in separate files, following the same
main.py/schemas.py-style separation already used in this package.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException
from index_engine import IndexConfig, InsufficientDataError

from forecasting import (
    build_booking_horizon_datasets,
    build_forecasting_dataset,
    compare_to_mospi_cpi,
    evaluate_all_routes,
    evaluate_national_baselines,
    evaluate_route_baselines,
    forecast_all_routes,
    forecast_national_index,
    forecast_route_index,
    load_mospi_cpi_series,
)

from .forecasting_schemas import (
    AllRoutesEvaluateRequest,
    AllRoutesForecastRequest,
    BookingHorizonRequest,
    BookingHorizonResultOut,
    BookingWindowPeriodOut,
    BookingWindowResultOut,
    CPIBenchmarkRequest,
    CPIBenchmarkResultOut,
    ForecastDatasetRequest,
    ForecastResultOut,
    ModelEvaluationResultOut,
    NationalEvaluateRequest,
    NationalForecastRequest,
    RouteEvaluateRequest,
    RouteForecastRequest,
)

router = APIRouter(prefix="/forecast", tags=["forecasting"])

#: The project's own bundled real MoSPI CPI extract -- see
#: ``data/benchmarks/README.md`` / ``docs/forecasting_methodology.md``.
#: No client-supplied path is accepted (see ``CPIBenchmarkRequest``'s
#: docstring): a fixed server-side path avoids an arbitrary-file-read
#: surface for essentially no functional benefit at this stage.
_MOSPI_CPI_PATH = Path(__file__).resolve().parent.parent / "data" / "benchmarks" / "cpi_1337.xlsx"


def _build_config(base_period: str, config_in) -> IndexConfig:
    if config_in is None:
        return IndexConfig(base_period=base_period)
    return IndexConfig(base_period=base_period, **config_in.model_dump())


def _build_weights(weights_in):
    if not weights_in:
        return None
    return pd.DataFrame([w.model_dump() for w in weights_in])


def _build_observations(observations_in) -> pd.DataFrame:
    return pd.DataFrame([obs.model_dump() for obs in observations_in])


def _dataset_from_request(request: ForecastDatasetRequest):
    """Shared dataset-building step for every forecasting endpoint below
    -- calls ``forecasting.build_forecasting_dataset`` unchanged, the same
    function Stage 1-4's own tests already exercise. Raises
    ``HTTPException`` (422/400, mirroring ``/index/calculate``'s existing
    convention) for genuine input problems; never fabricates a dataset.
    """
    config = _build_config(request.base_period, request.config)
    weights = _build_weights(request.weights)
    observations = _build_observations(request.observations)
    try:
        return build_forecasting_dataset(
            observations=observations,
            base_period=request.base_period,
            periods=request.periods,
            weights=weights,
            config=config,
        )
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/national", response_model=ForecastResultOut)
def forecast_national(request: NationalForecastRequest):
    """National index forecast -- wraps ``forecasting.forecast_national_index``."""
    dataset = _dataset_from_request(request)
    try:
        result = forecast_national_index(
            dataset,
            is_synthetic_data=request.is_synthetic_data,
            model=request.model,
            horizon=request.horizon,
            window=request.window,
            min_coverage_rate=request.min_coverage_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()


@router.post("/national/evaluate", response_model=dict[str, ModelEvaluationResultOut])
def evaluate_national(request: NationalEvaluateRequest):
    """National baseline evaluation -- wraps ``forecasting.evaluate_national_baselines``."""
    dataset = _dataset_from_request(request)
    try:
        results = evaluate_national_baselines(
            dataset,
            is_synthetic_data=request.is_synthetic_data,
            models=request.models,
            min_train_size=request.min_train_size,
            window=request.window,
            min_coverage_rate=request.min_coverage_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {name: result.to_dict() for name, result in results.items()}


@router.post("/route", response_model=ForecastResultOut)
def forecast_route(request: RouteForecastRequest):
    """Route-level forecast -- wraps ``forecasting.forecast_route_index``."""
    dataset = _dataset_from_request(request)
    try:
        result = forecast_route_index(
            dataset,
            route=request.route,
            is_synthetic_data=request.is_synthetic_data,
            model=request.model,
            horizon=request.horizon,
            window=request.window,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()


@router.post("/route/evaluate", response_model=dict[str, ModelEvaluationResultOut])
def evaluate_route(request: RouteEvaluateRequest):
    """Route-level baseline evaluation -- wraps ``forecasting.evaluate_route_baselines``."""
    dataset = _dataset_from_request(request)
    try:
        results = evaluate_route_baselines(
            dataset,
            route=request.route,
            is_synthetic_data=request.is_synthetic_data,
            models=request.models,
            min_train_size=request.min_train_size,
            window=request.window,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {name: result.to_dict() for name, result in results.items()}


@router.post("/routes", response_model=dict[str, ForecastResultOut])
def forecast_routes(request: AllRoutesForecastRequest):
    """Forecast for every route in the dataset -- wraps ``forecasting.forecast_all_routes``.
    A route with insufficient history reports its own INSUFFICIENT_DATA
    entry; it never prevents another route's entry from being returned.
    """
    dataset = _dataset_from_request(request)
    results = forecast_all_routes(
        dataset,
        is_synthetic_data=request.is_synthetic_data,
        model=request.model,
        horizon=request.horizon,
        window=request.window,
    )
    return {route: result.to_dict() for route, result in results.items()}


@router.post("/routes/evaluate", response_model=dict[str, dict[str, ModelEvaluationResultOut]])
def evaluate_routes(request: AllRoutesEvaluateRequest):
    """Baseline evaluation for every route -- wraps ``forecasting.evaluate_all_routes``."""
    dataset = _dataset_from_request(request)
    try:
        results = evaluate_all_routes(
            dataset,
            is_synthetic_data=request.is_synthetic_data,
            models=request.models,
            min_train_size=request.min_train_size,
            window=request.window,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        route: {name: result.to_dict() for name, result in per_model.items()} for route, per_model in results.items()
    }


@router.post("/cpi-benchmark", response_model=CPIBenchmarkResultOut)
def cpi_benchmark(request: CPIBenchmarkRequest):
    """CPI benchmark/comparison against MoSPI's official CPI Airfare
    sub-index -- wraps ``forecasting.compare_to_mospi_cpi``. Preserves the
    three-way ``yoy_comparison_status`` (INSUFFICIENT_OVERLAP /
    INSUFFICIENT_DATA / OK) and the separate MoM fields exactly as
    produced by the forecasting layer -- never collapsed or reinterpreted
    here. ``is_synthetic_airfare_data`` is always present in the response.
    """
    dataset = _dataset_from_request(request)
    if not _MOSPI_CPI_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"MoSPI CPI reference file not found at {_MOSPI_CPI_PATH} -- cannot run a CPI benchmark.",
        )
    mospi = load_mospi_cpi_series(_MOSPI_CPI_PATH)
    result = compare_to_mospi_cpi(
        dataset,
        mospi,
        is_synthetic_airfare_data=request.is_synthetic_data,
        min_coverage_rate=request.min_coverage_rate,
        exclude_mospi_imputed=request.exclude_mospi_imputed,
    )
    return result.to_dict()


@router.post("/booking-horizon", response_model=BookingHorizonResultOut)
def booking_horizon(request: BookingHorizonRequest):
    """Booking-horizon (T+1..T+45) analysis -- wraps
    ``forecasting.build_booking_horizon_datasets`` unchanged. That
    function's entry point takes scraper-JSONL file path(s), so the
    observations posted here are written to a short-lived temp file and
    handed to it as-is; no windowing/partitioning math is reimplemented in
    this route.
    """
    config = _build_config(request.base_period, request.config)
    weights = _build_weights(request.weights)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        for record in request.observations:
            tmp.write(json.dumps(record) + "\n")
        tmp_path = tmp.name

    try:
        analysis = build_booking_horizon_datasets(
            paths=[tmp_path],
            base_period=request.base_period,
            periods=request.periods,
            weights=weights,
            config=config,
            allow_mock=request.allow_mock,
        )
    except (InsufficientDataError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    windows_out = {}
    for name, window_dataset in analysis.windows.items():
        national_rows = []
        if window_dataset.dataset is not None:
            for row in window_dataset.dataset.national.to_dict(orient="records"):
                national_rows.append(
                    BookingWindowPeriodOut(
                        period=row["period"],
                        national_index=row.get("national_index"),
                        quality_flags=row.get("quality_flags"),
                    )
                )
        windows_out[name] = BookingWindowResultOut(
            window=window_dataset.window,
            record_count=window_dataset.record_count,
            status=window_dataset.status,
            error=window_dataset.error,
            national=national_rows,
        )

    return BookingHorizonResultOut(
        windows=windows_out,
        total_records_loaded=analysis.total_records_loaded,
        skipped_malformed_count=analysis.skipped_malformed_count,
        real_record_count=analysis.real_record_count,
        synthetic_record_count=analysis.synthetic_record_count,
        is_synthetic_data=analysis.is_synthetic_data,
        is_mixed_data=analysis.is_mixed_data,
        warnings=analysis.warnings,
    )
