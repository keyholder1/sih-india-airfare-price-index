"""Pydantic request/response schemas for the forecasting API layer.

Mirrors ``api/schemas.py``'s convention: kept separate from the
``forecasting`` package's own dataclasses so that package has zero
dependency on pydantic/FastAPI. Every response model here is a field-for-
field mirror of the corresponding ``forecasting`` dataclass (see
``forecasting.results``, ``forecasting.cpi_results``) -- nothing is
recomputed or reshaped beyond JSON translation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .schemas import FareObservationIn, IndexConfigIn, RouteWeightIn

__all__ = [
    "ForecastDatasetRequest",
    "NationalForecastRequest",
    "NationalEvaluateRequest",
    "RouteForecastRequest",
    "RouteEvaluateRequest",
    "AllRoutesForecastRequest",
    "AllRoutesEvaluateRequest",
    "CPIBenchmarkRequest",
    "BookingHorizonRequest",
    "ForecastResultOut",
    "ModelEvaluationResultOut",
    "CPIPeriodComparisonOut",
    "CPIBenchmarkResultOut",
    "BookingWindowPeriodOut",
    "BookingWindowResultOut",
    "BookingHorizonResultOut",
]


class ForecastDatasetRequest(BaseModel):
    """Shared shape for any endpoint that builds a ``ForecastingDataset``
    from raw fare observations before forecasting on it -- same
    observation/weights/config schema ``/index/calculate`` already uses
    (see ``api/schemas.py``), so a caller who already has index-engine
    payloads can reuse them unchanged.
    """

    base_period: str = Field(..., description="YYYY-MM period pinned to index value 100")
    periods: Optional[List[str]] = Field(
        default=None, description="Explicit YYYY-MM periods; omit to derive from observations"
    )
    observations: List[FareObservationIn]
    weights: Optional[List[RouteWeightIn]] = None
    config: Optional[IndexConfigIn] = None
    is_synthetic_data: bool = Field(
        ...,
        description=(
            "REQUIRED, no default -- the caller must state explicitly whether `observations` are "
            "real or synthetic fare data. Never silently assumed; see forecasting.national's "
            "module docstring for why."
        ),
    )


class NationalForecastRequest(ForecastDatasetRequest):
    model: str = "naive"
    horizon: int = 1
    window: int = 3
    min_coverage_rate: Optional[float] = None


class NationalEvaluateRequest(ForecastDatasetRequest):
    models: Optional[List[str]] = None
    min_train_size: int = 1
    window: int = 3
    min_coverage_rate: Optional[float] = None


class RouteForecastRequest(ForecastDatasetRequest):
    route: str
    model: str = "naive"
    horizon: int = 1
    window: int = 3


class RouteEvaluateRequest(ForecastDatasetRequest):
    route: str
    models: Optional[List[str]] = None
    min_train_size: int = 1
    window: int = 3


class AllRoutesForecastRequest(ForecastDatasetRequest):
    model: str = "naive"
    horizon: int = 1
    window: int = 3


class AllRoutesEvaluateRequest(ForecastDatasetRequest):
    models: Optional[List[str]] = None
    min_train_size: int = 1
    window: int = 3


class CPIBenchmarkRequest(ForecastDatasetRequest):
    """No MoSPI file path is accepted from the client -- the server always
    loads its own bundled ``data/benchmarks/cpi_1337.xlsx`` extract, the
    same file ``tests/test_cpi_benchmark.py`` and the forecasting stages
    use. Accepting an arbitrary client-supplied path would be a path-
    traversal / arbitrary-file-read risk for no real benefit at this
    prototype stage.
    """

    min_coverage_rate: Optional[float] = None
    exclude_mospi_imputed: bool = True


class BookingHorizonRequest(BaseModel):
    """Booking-horizon analysis needs each observation's raw
    ``booking_date``/``flight_date`` pair *and* its ``is_mock`` flag
    (scraper-output shape), which ``FareObservationIn`` doesn't carry --
    so this endpoint accepts loosely-typed observation dicts matching
    scraper JSONL records directly, the same shape
    ``forecasting.booking_horizon.build_booking_horizon_datasets`` already
    expects, rather than a narrower schema that would need translating.
    """

    base_period: str
    periods: Optional[List[str]] = None
    observations: List[Dict[str, Any]]
    weights: Optional[List[RouteWeightIn]] = None
    config: Optional[IndexConfigIn] = None
    allow_mock: bool = False


class ForecastResultOut(BaseModel):
    forecast_period: str
    forecast_value: Optional[float]
    model_used: str
    horizon: int
    training_period: List[str]
    data_points_used: int
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    status: str
    is_synthetic_data: bool
    notes: Optional[str] = None


class ModelEvaluationResultOut(BaseModel):
    model: str
    number_of_forecasts: int
    mae: Optional[float]
    rmse: Optional[float]
    mase: Optional[float]
    mase_status: str
    status: str
    notes: Optional[str] = None
    forecasts: List[ForecastResultOut] = Field(default_factory=list)


class CPIPeriodComparisonOut(BaseModel):
    period: str
    our_index_rebased: Optional[float]
    mospi_index_rebased: Optional[float]
    our_mom_pct: Optional[float]
    mospi_mom_pct: Optional[float]
    mom_difference_pct_points: Optional[float]
    our_yoy_pct: Optional[float]
    mospi_yoy_pct: Optional[float]
    yoy_difference_pct_points: Optional[float]
    mospi_imputed: bool
    included_in_metrics: bool
    exclusion_reason: Optional[str] = None


class CPIBenchmarkResultOut(BaseModel):
    overlap_start: Optional[str]
    overlap_end: Optional[str]
    overlap_period_count: int
    rebase_period: Optional[str]
    comparisons: List[CPIPeriodComparisonOut]
    mean_absolute_mom_difference_pct_points: Optional[float]
    mom_correlation: Optional[float]
    mom_correlation_status: str
    yoy_comparison_status: str
    mean_absolute_yoy_difference_pct_points: Optional[float]
    yoy_period_count: int
    mospi_base_year: Optional[int]
    mospi_source_file: Optional[str]
    status: str
    is_synthetic_airfare_data: bool
    notes: Optional[str] = None


class BookingWindowPeriodOut(BaseModel):
    period: str
    national_index: Optional[float]
    quality_flags: Optional[str] = None


class BookingWindowResultOut(BaseModel):
    window: str
    record_count: int
    status: str
    error: Optional[str] = None
    national: List[BookingWindowPeriodOut] = Field(default_factory=list)


class BookingHorizonResultOut(BaseModel):
    windows: Dict[str, BookingWindowResultOut]
    total_records_loaded: int
    skipped_malformed_count: int
    real_record_count: int
    synthetic_record_count: int
    is_synthetic_data: bool
    is_mixed_data: bool
    warnings: List[str] = Field(default_factory=list)
