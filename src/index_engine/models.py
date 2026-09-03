"""Typed result structures returned by the index engine.

Kept as plain dataclasses (rather than pydantic or similar) so this module
has no dependency beyond the standard library and can be serialized by
whatever the backend team ends up using (FastAPI, Flask, Django...).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class CleaningReport:
    """Accounting of what happened to every input observation."""

    total_input: int
    total_valid: int
    total_removed: int
    removed_by_reason: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RouteIndexResult:
    """Result of index calculation for a single route at a single period."""

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
    status: str  # see quality.RouteStatus

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RouteContribution:
    """How much a route contributed to the national index's MoM change."""

    route: str
    weight_normalized: float
    route_index_current: Optional[float]
    route_index_previous: Optional[float]
    contribution_points: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IndexResult:
    """Full output of :meth:`AirfarePriceIndex.calculate`."""

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
    route_indices: List[RouteIndexResult]
    route_contributions: List[RouteContribution]
    quality_flags: List[str]
    cleaning_report: CleaningReport
    # Additional quality/coverage accounting, named to match what a
    # dashboard's "data quality" panel typically wants to show. These are
    # derived from the fields above (routes_expected == routes_total,
    # routes_covered is the "used" count) — kept as separate named fields
    # because backend/dashboard consumers asked for this exact vocabulary.
    observations_received: int = 0
    observations_rejected: int = 0
    outliers_flagged: int = 0
    routes_expected: int = 0
    routes_with_data: int = 0

    def to_dict(self) -> dict:
        return {
            "base_period": self.base_period,
            "current_period": self.current_period,
            "national_index": self.national_index,
            "mom_change_pct": self.mom_change_pct,
            "yoy_change_pct": self.yoy_change_pct,
            "routes_covered": self.routes_covered,
            "routes_total": self.routes_total,
            "observations_used": self.observations_used,
            "coverage_rate": self.coverage_rate,
            "observations_received": self.observations_received,
            "observations_rejected": self.observations_rejected,
            "outliers_flagged": self.outliers_flagged,
            "routes_expected": self.routes_expected,
            "routes_with_data": self.routes_with_data,
            "representative_method": self.representative_method,
            "aggregation_method": self.aggregation_method,
            "route_indices": [r.to_dict() for r in self.route_indices],
            "route_contributions": [c.to_dict() for c in self.route_contributions],
            "quality_flags": self.quality_flags,
            "cleaning_report": self.cleaning_report.to_dict(),
        }
