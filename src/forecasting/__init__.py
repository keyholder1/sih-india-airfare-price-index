"""Forecasting module for the SIH Airfare Price Index project.

STAGE 1 (complete): data-access and preparation layer.
STAGE 2 (complete): data exploration (no new code — see docs/).
STAGE 3 (complete): national-level baseline forecasting + backtesting.
STAGE 3.1 (complete): real-data readiness fixes.
CPI BENCHMARK (complete): structural comparison pipeline against MoSPI's
official CPI Airfare sub-index, including a real month-over-month AND
year-over-year comparison (YoY requires a genuine 12-months-apart pair
on both sides — never fabricated) — see cpi_benchmark.py's module
docstring for why this is a structural pipeline, not a validation claim,
while the project's fare data remains synthetic.
SCRAPER INGEST (complete): thin adapter turning scraper-output JSONL files
into a ForecastingDataset — see ingest.py's module docstring. Does not
duplicate index_engine or data_quality logic.
ROUTE-LEVEL FORECASTING (complete): per-route baseline forecasting and
backtesting, mirroring the national-level architecture exactly — see
route.py's module docstring.
BOOKING-HORIZON ANALYTICS (current): partitions raw scraper observations
into T+1..T+45 advance-purchase windows and builds one ForecastingDataset
per window, reusing build_forecasting_dataset() unchanged — see
booking_horizon.py's module docstring.

This package builds a forecasting-ready HISTORICAL dataset (national-level
and route-level time series) from index_engine's own public output, and
now also produces simple, explainable baseline forecasts and rolling-origin
backtests on top of it, at both the national and route level. It does not
compute, recompute, or duplicate any index/aggregation/cleaning logic —
index_engine remains the single source of truth for the price index itself.

Later stages (not built yet): multi-step-horizon forecasting, advanced
models, anomaly detection, alerts.

Public API:

    from forecasting import build_forecasting_dataset, forecast_national_index

    dataset = build_forecasting_dataset(fares_df, base_period="2026-01")
    dataset.national            # one row per period
    dataset.routes              # one row per (route, period), every status kept

    forecast = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    evaluations = evaluate_national_baselines(dataset, is_synthetic_data=True)
"""

from .backtesting import rolling_origin_backtest
from .baseline_models import BASELINE_MODELS, historical_mean_forecast, moving_average_forecast, naive_forecast
from .data_access import (
    DEFAULT_MAX_FUTURE_DAYS,
    DEFAULT_MAX_PAST_YEARS,
    NATIONAL_COLUMNS,
    ROUTE_COLUMNS,
    ForecastingDataset,
    build_forecasting_dataset,
    derive_calendar_periods,
)
from .dtypes import to_numeric_safe
from .national import evaluate_national_baselines, forecast_national_index
from .route import (
    evaluate_all_routes,
    evaluate_route_baselines,
    forecast_all_routes,
    forecast_route_index,
)
from .results import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MODEL_NOT_APPLICABLE,
    STATUS_OK,
    STATUS_TARGET_UNAVAILABLE,
    ForecastResult,
    ModelEvaluationResult,
)
from .series import national_index_series, route_index_series
from .cpi_loader import MospiCpiSeries, load_mospi_cpi_series
from .cpi_results import (
    STATUS_INSUFFICIENT_OVERLAP,
    CPIBenchmarkResult,
    CPIPeriodComparison,
)
from .cpi_benchmark import compare_to_mospi_cpi
from .ingest import ScraperIngestResult, build_dataset_from_scraper_output, load_scraper_jsonl
from .booking_horizon import (
    BOOKING_WINDOWS,
    BookingHorizonAnalysis,
    BookingHorizonPartition,
    BookingWindow,
    BookingWindowDataset,
    build_booking_horizon_datasets,
    classify_booking_window,
    compute_advance_purchase_days,
    partition_by_booking_window,
)

__all__ = [
    # Stage 1
    "ForecastingDataset",
    "build_forecasting_dataset",
    "derive_calendar_periods",
    "NATIONAL_COLUMNS",
    "ROUTE_COLUMNS",
    "DEFAULT_MAX_PAST_YEARS",
    "DEFAULT_MAX_FUTURE_DAYS",
    # Stage 3
    "ForecastResult",
    "ModelEvaluationResult",
    "BASELINE_MODELS",
    "naive_forecast",
    "historical_mean_forecast",
    "moving_average_forecast",
    "rolling_origin_backtest",
    "national_index_series",
    "forecast_national_index",
    "evaluate_national_baselines",
    # Route-level forecasting
    "route_index_series",
    "forecast_route_index",
    "evaluate_route_baselines",
    "forecast_all_routes",
    "evaluate_all_routes",
    # Stage 3 / CPI shared status constants (STATUS_OK/STATUS_INSUFFICIENT_DATA
    # are shared between forecasting.results and forecasting.cpi_results —
    # each module still owns its own definition, these are just re-exported
    # here for a single top-level import path, not duplicated).
    "STATUS_OK",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_MODEL_NOT_APPLICABLE",
    "STATUS_TARGET_UNAVAILABLE",
    "STATUS_INSUFFICIENT_OVERLAP",
    # Stage 3.1
    "to_numeric_safe",
    # CPI benchmark
    "MospiCpiSeries",
    "load_mospi_cpi_series",
    "CPIBenchmarkResult",
    "CPIPeriodComparison",
    "compare_to_mospi_cpi",
    # Scraper ingest
    "ScraperIngestResult",
    "build_dataset_from_scraper_output",
    "load_scraper_jsonl",
    # Booking-horizon analytics
    "BOOKING_WINDOWS",
    "BookingWindow",
    "BookingHorizonPartition",
    "BookingWindowDataset",
    "BookingHorizonAnalysis",
    "compute_advance_purchase_days",
    "classify_booking_window",
    "partition_by_booking_window",
    "build_booking_horizon_datasets",
]

__version__ = "0.8.0"
