"""Pydantic request/response schemas for the index engine HTTP wrapper.

Kept separate from index_engine's own dataclasses (index_engine.models) so
the core engine has zero dependency on pydantic/FastAPI — this layer only
translates between JSON and the engine's plain Python objects.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FareObservationIn(BaseModel):
    """One fare observation. Extra fields (source, timestamp, fare_class,
    etc.) are accepted and passed straight through to the engine."""

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


class CalculateRequest(BaseModel):
    base_period: str = Field(..., description="YYYY-MM period pinned to index value 100")
    current_period: str = Field(..., description="YYYY-MM period to calculate the index for")
    observations: List[FareObservationIn]
    weights: Optional[List[RouteWeightIn]] = Field(
        default=None, description="Omit to use clearly-labelled synthetic demo weights"
    )
    config: Optional[IndexConfigIn] = None


class TimeseriesRequest(BaseModel):
    base_period: str
    periods: List[str] = Field(..., description="YYYY-MM periods to calculate, in order")
    observations: List[FareObservationIn]
    weights: Optional[List[RouteWeightIn]] = None
    config: Optional[IndexConfigIn] = None


class RouteIndexOut(BaseModel):
    route: str
    origin: str
    destination: str
    period: str
    base_period_fare: Optional[float]
    period_fare: Optional[float]
    route_index: Optional[float]
    observations_used: int
    weight_raw: Optional[float]
    weight_normalized: Optional[float]
    status: str


class RouteContributionOut(BaseModel):
    route: str
    weight_normalized: float
    route_index_current: Optional[float]
    route_index_previous: Optional[float]
    contribution_points: Optional[float]


class CleaningReportOut(BaseModel):
    total_input: int
    total_valid: int
    total_removed: int
    removed_by_reason: Dict[str, int]


class IndexResultOut(BaseModel):
    base_period: str
    current_period: str
    national_index: Optional[float]
    mom_change_pct: Optional[float]
    yoy_change_pct: Optional[float]
    routes_covered: int
    routes_total: int
    observations_used: int
    coverage_rate: float
    representative_method: str
    aggregation_method: str
    route_indices: List[RouteIndexOut]
    route_contributions: List[RouteContributionOut]
    quality_flags: List[str]
    cleaning_report: CleaningReportOut
    observations_received: int
    observations_rejected: int
    outliers_flagged: int
    routes_expected: int
    routes_with_data: int


class ErrorOut(BaseModel):
    error: str
    detail: str
