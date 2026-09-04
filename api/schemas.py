"""
Pydantic models for every API request and response body.

Every response field is documented with ``Field(..., description=...)``
so it appears in the auto-generated Swagger/OpenAPI docs.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ── Common ────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error envelope returned for all non-2xx responses."""

    detail: str = Field(..., description="Human-readable error message.")

    model_config = {"json_schema_extra": {"examples": [{"detail": "Invalid date format. Expected YYYY-MM."}]}}


class PaginationMeta(BaseModel):
    """Pagination metadata included in paginated responses."""

    total: int = Field(..., description="Total number of records available.")
    limit: int = Field(..., description="Page size used for this response.")
    offset: int = Field(..., description="Offset from the start of the result set.")
    has_more: bool = Field(..., description="Whether more records exist beyond this page.")


# ── Index ─────────────────────────────────────────────────────────


class ObservationInput(BaseModel):
    """A single airfare observation."""

    route: str = Field(
        ...,
        description="IATA route code, e.g. 'DEL-BOM'.",
        min_length=7,
        max_length=7,
        json_schema_extra={"examples": ["DEL-BOM"]},
    )
    fare: float = Field(
        ...,
        description="Observed fare in INR. Must be positive.",
        gt=0,
    )
    date: str = Field(
        ...,
        description="Observation date in YYYY-MM-DD format.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    source: str = Field(
        ...,
        description="Data source label: 'real' or 'synthetic'.",
        json_schema_extra={"examples": ["real"]},
    )


class IndexCalculateRequest(BaseModel):
    """Request body for POST /api/v1/index/calculate."""

    observations: list[ObservationInput] = Field(
        ...,
        description="List of airfare observations to include in the index calculation.",
        min_length=1,
    )
    base_period: str = Field(
        ...,
        description="Base period in YYYY-MM format.",
        pattern=r"^\d{4}-\d{2}$",
    )
    current_period: str = Field(
        ...,
        description="Current period in YYYY-MM format.",
        pattern=r"^\d{4}-\d{2}$",
    )
    config: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional engine-specific configuration overrides.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "observations": [
                        {"route": "DEL-BOM", "fare": 4500, "date": "2026-08-15", "source": "real"},
                    ],
                    "base_period": "2026-01",
                    "current_period": "2026-08",
                    "config": {},
                }
            ]
        }
    }


# ── Forecasting support ─────────────────────────────────────────────
# The forecasting endpoints (api/forecasting_routes.py) work directly off
# raw fare observations, same as the underlying index_engine/forecasting
# packages, rather than the simplified route/fare/date/source shape
# ObservationInput uses above -- a caller with data_contract.md-shaped
# payloads (e.g. from the scraper) can pass them through unchanged.


class FareObservationIn(BaseModel):
    """One fare observation, full data_contract.md shape. Extra fields
    (source, timestamp, fare_class, etc.) are accepted and passed
    straight through to the engine."""

    model_config = {"extra": "allow"}

    observation_id: str
    airline: str
    origin: str
    destination: str
    flight_date: str
    booking_date: str
    total_fare: float
    currency: str


class RouteWeightIn(BaseModel):
    origin: str
    destination: str
    weight: float
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    source: Optional[str] = None


class IndexConfigIn(BaseModel):
    representative_method: str = "median"
    trimmed_mean_proportion: float = 0.1
    outlier_method: str = "iqr"
    outlier_iqr_multiplier: float = 1.5
    fare_field: str = "total_fare"
    booking_horizon_filter: Optional[str] = None
    min_observations_per_route_period: int = 3
    aggregation_method: str = "arithmetic"


class RouteIndexResponse(BaseModel):
    """Index result for a single route."""

    route: str = Field(..., description="IATA route code.")
    index: Optional[float] = Field(..., description="Route-level index value. Null when this route had no computable index (e.g. no base-period fare) -- never fabricated.")
    mom: Optional[float] = Field(None, description="Month-over-month change (%).")
    weight: float = Field(..., description="Weight of this route in the composite index.")
    contribution: float = Field(..., description="Absolute contribution to the national index.")
    data_source: str = Field(..., description="'real', 'synthetic', 'mixed', or 'unavailable'.")


class IndexCalculateResponse(BaseModel):
    """Response for POST /api/v1/index/calculate."""

    national_index: Optional[float] = Field(..., description="Composite national airfare price index value. Null when there was no coverage to compute one -- never fabricated.")
    mom: Optional[float] = Field(None, description="Month-over-month change (%).")
    yoy: Optional[float] = Field(None, description="Year-over-year change (%).")
    base_period: str = Field(..., description="Base period used.")
    current_period: str = Field(..., description="Current period used.")
    route_indices: list[RouteIndexResponse] = Field(..., description="Per-route index breakdowns.")
    quality_score: Optional[float] = Field(None, description="Quality score (0-1) for the input data.")
    flags: list[str] = Field(default_factory=list, description="Processing flags and warnings.")
    data_source: str = Field(..., description="'real', 'synthetic', 'mixed', or 'unavailable'. Indicates whether the result is computed from real, stub, or a mix of both kinds of data.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional engine metadata.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "national_index": 105.5,
                    "mom": 1.2,
                    "yoy": 3.5,
                    "base_period": "2026-01",
                    "current_period": "2026-08",
                    "route_indices": [
                        {"route": "DEL-BOM", "index": 107.2, "mom": 1.5, "weight": 0.25, "contribution": 26.8, "data_source": "synthetic"}
                    ],
                    "quality_score": 0.92,
                    "flags": ["stub_data"],
                    "data_source": "synthetic",
                    "metadata": {"engine": "stub"},
                }
            ]
        }
    }


# ── Timeseries ────────────────────────────────────────────────────


class TimeseriesPointResponse(BaseModel):
    """A single point in the index time series."""

    period: str = Field(..., description="Period in YYYY-MM format.")
    index: Optional[float] = Field(..., description="Index value for this period. Null when no index could be computed for this period -- never fabricated as a plausible-looking drift value.")
    mom: Optional[float] = Field(None, description="Month-over-month change (%).")
    yoy: Optional[float] = Field(None, description="Year-over-year change (%).")
    data_source: str = Field(..., description="'real', 'synthetic', 'mixed', or 'unavailable' -- 'unavailable' when index is null.")


class TimeseriesResponse(BaseModel):
    """Response for GET /api/v1/index/timeseries."""

    data: list[TimeseriesPointResponse] = Field(..., description="Time series data points.")
    pagination: PaginationMeta = Field(..., description="Pagination metadata.")
    data_source: str = Field(..., description="'real', 'synthetic', 'mixed', or 'unavailable'. Summarizes the observation batch this series was computed from; individual points may still differ (see each point's own data_source).")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {"period": "2026-01", "index": 100.0, "mom": None, "yoy": 2.5, "data_source": "synthetic"},
                        {"period": "2026-02", "index": 100.8, "mom": 0.8, "yoy": 2.3, "data_source": "synthetic"},
                    ],
                    "pagination": {"total": 8, "limit": 100, "offset": 0, "has_more": False},
                    "data_source": "synthetic",
                }
            ]
        }
    }


# ── Routes ────────────────────────────────────────────────────────


class RouteAnalysisResponse(BaseModel):
    """Analysis result for a single route."""

    route: str = Field(..., description="IATA route code.")
    route_index: Optional[float] = Field(..., description="Route-level index value. Null when no index could be computed for this route -- never fabricated.")
    mom: Optional[float] = Field(None, description="Month-over-month movement (%).")
    weight: float = Field(..., description="Weight in the composite index.")
    contribution: float = Field(..., description="Absolute contribution to the national index.")
    traffic_coverage: float = Field(..., description="Estimated traffic coverage (0-1).")
    status: str = Field(..., description="Route status: 'active', 'inactive', or 'new'.")
    data_source: str = Field(..., description="'real', 'synthetic', 'mixed', or 'unavailable'.")


class RouteListResponse(BaseModel):
    """Response for GET /api/v1/routes."""

    routes: list[RouteAnalysisResponse] = Field(..., description="List of route analysis results.")
    data_source: str = Field(..., description="'real' or 'synthetic'.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "routes": [
                        {
                            "route": "DEL-BOM",
                            "route_index": 107.2,
                            "mom": 1.5,
                            "weight": 0.125,
                            "contribution": 13.4,
                            "traffic_coverage": 0.85,
                            "status": "active",
                            "data_source": "synthetic",
                        }
                    ],
                    "data_source": "synthetic",
                }
            ]
        }
    }


# ── Quality ───────────────────────────────────────────────────────


class RouteHealthResponse(BaseModel):
    """Health assessment for a single route."""

    route: str = Field(..., description="IATA route code.")
    observations: int = Field(..., description="Total observations for this route.")
    valid: int = Field(..., description="Valid observations.")
    rejected: int = Field(..., description="Rejected observations.")
    flagged: int = Field(..., description="Flagged observations requiring review.")
    health_score: float = Field(..., description="Route health score (0-1).")
    status: str = Field(..., description="'healthy', 'degraded', or 'critical'.")


class SourceHealthResponse(BaseModel):
    """Health assessment for a data source."""

    source: str = Field(..., description="Data source identifier.")
    observations: int = Field(..., description="Total observations from this source.")
    valid: int = Field(..., description="Valid observations.")
    rejected: int = Field(..., description="Rejected observations.")
    reliability_score: float = Field(..., description="Source reliability score (0-1).")


class QualityResponse(BaseModel):
    """Response for GET /api/v1/quality."""

    total_observations: int = Field(..., description="Total observations assessed.")
    valid: int = Field(..., description="Observations that passed validation.")
    rejected: int = Field(..., description="Observations rejected.")
    flagged: int = Field(..., description="Observations flagged for review.")
    rejection_reasons: dict[str, int] = Field(..., description="Count of rejections by reason.")
    quality_score: float = Field(..., description="Overall quality score (0-1).")
    quality_grade: str = Field(..., description="Quality grade: A, B, C, D, or F.")
    route_health: list[RouteHealthResponse] = Field(..., description="Per-route health assessments.")
    source_health: list[SourceHealthResponse] = Field(..., description="Per-source health assessments.")
    data_source: str = Field(..., description="'real' or 'synthetic'.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_observations": 150,
                    "valid": 135,
                    "rejected": 7,
                    "flagged": 8,
                    "rejection_reasons": {"fare_out_of_range": 4, "duplicate": 3},
                    "quality_score": 0.90,
                    "quality_grade": "A",
                    "route_health": [],
                    "source_health": [],
                    "data_source": "synthetic",
                }
            ]
        }
    }


# ── News / Context ────────────────────────────────────────────────


class NewsEventResponse(BaseModel):
    """A single news or event item relevant to a route."""

    headline: str = Field(..., description="News headline.")
    source: str = Field(..., description="News source name.")
    publication_date: str = Field(..., description="Publication date (YYYY-MM-DD).")
    url: Optional[str] = Field(None, description="Original article URL, if available.")
    relevance_score: float = Field(..., description="Relevance score (0-1) relative to the route's fare movement.")
    data_source: str = Field(..., description="'real' or 'synthetic'.")


class NaturalEventResponse(BaseModel):
    """One real NASA EONET natural event matched to a route's price
    movement -- contextual only, never a claimed cause. See
    docs/eonet_context.md."""

    event_id: str = Field(..., description="EONET event id, e.g. 'EONET_23868'.")
    title: str = Field(..., description="EONET's own event title.")
    category: str = Field(..., description="EONET category id, e.g. 'severeStorms'.")
    category_label: str = Field(..., description="Human-readable category label.")
    category_emoji: str = Field(..., description="Display emoji for the category.")
    event_date: str = Field(..., description="ISO 8601 event date (latest recorded position/date).")
    distance_from_origin_km: Optional[float] = Field(None, description="Great-circle distance from the route's origin airport, km.")
    distance_from_destination_km: Optional[float] = Field(None, description="Great-circle distance from the route's destination airport, km.")
    temporal_distance_days: float = Field(..., description="Days between the event and the route's movement date.")
    relevance_score: float = Field(..., description="Relevance score (0-1) -- geographic + temporal proximity, not causal.")
    relevance_reason: list[str] = Field(..., description="Plain-language reasons this event matched.")
    source_url: Optional[str] = Field(None, description="Original EONET/source URL, if available.")
    is_closed: bool = Field(..., description="Whether EONET has marked this event closed.")


class WeatherConditionsResponse(BaseModel):
    """Current conditions at one airport (OpenWeatherMap) -- a live
    snapshot, not scored/ranked, never claimed as a cause of any fare
    movement."""

    iata_code: str = Field(..., description="IATA airport code.")
    city_name: str = Field(..., description="City name as returned by OpenWeatherMap.")
    observed_at: str = Field(..., description="ISO 8601 observation timestamp.")
    temperature_c: float = Field(..., description="Temperature, Celsius.")
    feels_like_c: float = Field(..., description="'Feels like' temperature, Celsius.")
    condition: str = Field(..., description="Short condition label, e.g. 'Rain'.")
    description: str = Field(..., description="Longer condition description.")
    wind_speed_ms: float = Field(..., description="Wind speed, m/s.")
    humidity_pct: int = Field(..., description="Relative humidity, %.")
    visibility_m: Optional[int] = Field(None, description="Visibility, metres, if reported.")


class RouteContextResponse(BaseModel):
    """Response for GET /api/v1/routes/{route}/context."""

    route: str = Field(..., description="IATA route code.")
    significant_movement: bool = Field(..., description="Whether the route has significant recent fare movement.")
    movement_direction: Optional[str] = Field(None, description="'up', 'down', or null.")
    movement_pct: Optional[float] = Field(None, description="Percentage of fare movement.")
    events: list[NewsEventResponse] = Field(..., description="Related news/events.")
    data_source: str = Field(..., description="'real' or 'synthetic'.")
    natural_events: list[NaturalEventResponse] = Field(
        default_factory=list, description="Real NASA EONET natural events matched to this route -- contextual only, never a claimed cause."
    )
    natural_events_status: str = Field("UNAVAILABLE", description="'OK' or 'UNAVAILABLE' -- whether the EONET fetch itself succeeded.")
    weather_origin: Optional[WeatherConditionsResponse] = Field(None, description="Current conditions at the origin airport, if available.")
    weather_destination: Optional[WeatherConditionsResponse] = Field(None, description="Current conditions at the destination airport, if available.")
    weather_status: str = Field("UNAVAILABLE", description="'OK', 'PARTIAL', or 'UNAVAILABLE'.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "route": "DEL-BOM",
                    "significant_movement": True,
                    "movement_direction": "up",
                    "movement_pct": 4.2,
                    "events": [
                        {
                            "headline": "Synthetic: Airfares on DEL-BOM rise amid holiday demand",
                            "source": "synthetic_news_source",
                            "publication_date": "2026-08-14",
                            "url": None,
                            "relevance_score": 0.87,
                            "data_source": "synthetic",
                        }
                    ],
                    "data_source": "synthetic",
                }
            ]
        }
    }


# ── Dashboard ─────────────────────────────────────────────────────


class CoverageInfo(BaseModel):
    """Traffic coverage summary."""

    total_routes: int = Field(..., description="Total number of tracked routes.")
    active_routes: int = Field(..., description="Number of currently active routes.")
    average_coverage: float = Field(..., description="Average traffic coverage across active routes (0-1).")


class AlertItem(BaseModel):
    """A dashboard alert or notification."""

    level: str = Field(..., description="Alert level: 'info', 'warning', or 'critical'.")
    message: str = Field(..., description="Alert message.")
    timestamp: Optional[str] = Field(None, description="When the alert was generated (ISO 8601).")


class DashboardSummaryResponse(BaseModel):
    """Response for GET /api/v1/dashboard/summary."""

    index: Optional[float] = Field(..., description="Current national index value. Null when no index could be computed -- never fabricated.")
    mom: Optional[float] = Field(None, description="Month-over-month change (%).")
    yoy: Optional[float] = Field(None, description="Year-over-year change (%).")
    routes: list[RouteAnalysisResponse] = Field(..., description="All tracked routes with their latest analysis.")
    top_increases: list[RouteAnalysisResponse] = Field(..., description="Routes with the largest positive MoM movement.")
    top_decreases: list[RouteAnalysisResponse] = Field(..., description="Routes with the largest negative MoM movement (or smallest positive).")
    top_contributors: list[RouteAnalysisResponse] = Field(..., description="Routes with the highest absolute contribution.")
    quality: QualityResponse = Field(..., description="Latest data quality summary.")
    coverage: CoverageInfo = Field(..., description="Route coverage information.")
    alerts: list[AlertItem] = Field(default_factory=list, description="Active alerts and notifications.")
    data_source: str = Field(..., description="'real' or 'synthetic'.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "index": 105.5,
                    "mom": 1.2,
                    "yoy": 3.5,
                    "routes": [],
                    "top_increases": [],
                    "top_decreases": [],
                    "top_contributors": [],
                    "quality": {
                        "total_observations": 150,
                        "valid": 135,
                        "rejected": 7,
                        "flagged": 8,
                        "rejection_reasons": {},
                        "quality_score": 0.90,
                        "quality_grade": "A",
                        "route_health": [],
                        "source_health": [],
                        "data_source": "synthetic",
                    },
                    "coverage": {"total_routes": 8, "active_routes": 6, "average_coverage": 0.72},
                    "alerts": [{"level": "info", "message": "Using synthetic stub data.", "timestamp": None}],
                    "data_source": "synthetic",
                }
            ]
        }
    }
