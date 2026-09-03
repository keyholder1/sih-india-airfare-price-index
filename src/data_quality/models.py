"""Typed, JSON-serializable result structures for the data quality layer.

Plain dataclasses (no pydantic dependency), matching the convention in
``index_engine.models`` so both modules' outputs compose cleanly for a
backend/dashboard consumer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CompletenessReport:
    total_records: int
    records_with_all_required_fields: int
    records_missing_required_fields: int
    records_missing_optional_fields: int
    completeness_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceHealth:
    """Health/trust metrics for one scraper source.

    ``routes_requested`` / ``routes_successful`` / ``routes_failed`` /
    ``route_success_rate`` are only populated when a ``route_attempts`` log
    was supplied to the pipeline — fare observations alone don't carry
    "routes we tried and got nothing back for". They are ``None``, not 0,
    when unavailable (0 would falsely claim total failure).
    """

    source: str
    status: str  # HEALTHY / DEGRADED / FAILED / UNKNOWN

    observations_received: int
    valid_observations: int
    flagged_observations: int
    rejected_observations: int
    observation_validity_rate: float

    routes_requested: Optional[int] = None
    routes_successful: Optional[int] = None
    routes_failed: Optional[int] = None
    route_success_rate: Optional[float] = None

    oldest_observation: Optional[str] = None
    newest_observation: Optional[str] = None
    data_age_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RouteHealth:
    """Data-quality-level quality for one origin-destination pair.

    Complements, and does not replace, ``index_engine``'s own per-route
    ``RouteIndexResult.status`` (NO_BASE_DATA / INSUFFICIENT_DATA / ...),
    which is about whether a *statistical index* could be computed. This is
    about whether the *raw observations* for that route look trustworthy.
    """

    route: str
    origin: str
    destination: str

    observations_total: int
    observations_valid: int  # VALID + FLAGGED (i.e. not REJECTED)
    observations_rejected: int
    route_quality_rate: float
    data_completeness: float

    has_base_period_data: Optional[bool] = None
    has_current_period_data: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataQualityResult:
    """Full output of :func:`data_quality.pipeline.validate_fare_batch`."""

    records_received: int
    records_valid: int
    records_flagged: int
    records_rejected: int

    completeness_rate: float
    validity_rate: float
    duplicate_rate: float

    quality_score: float
    quality_grade: str

    rejection_reasons: Dict[str, int]
    flag_reasons: Dict[str, int]

    duplicate_count: int
    exact_duplicate_count: int
    potential_duplicate_count: int

    completeness: CompletenessReport
    source_health: List[SourceHealth]
    route_health: List[RouteHealth]

    #: Records safe to hand to AirfarePriceIndex.calculate(...) — VALID and
    #: FLAGGED rows (everything not REJECTED). Flags are attention markers
    #: for a human/dashboard, not exclusions: the index engine's own
    #: statistical outlier detection is the authority on whether an unusual
    #: fare should actually be excluded (see docs/data_quality.md §separation
    #: of concerns). Original raw field values, not the internal working copy.
    valid_observations: List[Dict[str, Any]] = field(default_factory=list)

    #: Overall scraper effectiveness, only if any source supplied route
    #: attempt data; frontend-ready convenience fields (see §23 of the spec).
    overall_route_success_rate: Optional[float] = None
    overall_route_coverage: Optional[float] = None

    #: Per-record status/reason detail, index-aligned with the input batch
    #: (not the survivors) so a caller can reconcile 1:1 with what they sent.
    #: Kept out of to_dict() by default (can be large); use to_dict(include_records=True).
    record_results: List[Dict[str, Any]] = field(default_factory=list, repr=False)

    def to_dict(self, include_records: bool = False) -> dict:
        out = {
            "records_received": self.records_received,
            "records_valid": self.records_valid,
            "records_flagged": self.records_flagged,
            "records_rejected": self.records_rejected,
            "completeness_rate": self.completeness_rate,
            "validity_rate": self.validity_rate,
            "duplicate_rate": self.duplicate_rate,
            "quality_score": self.quality_score,
            "quality_grade": self.quality_grade,
            "rejection_reasons": self.rejection_reasons,
            "flag_reasons": self.flag_reasons,
            "duplicate_count": self.duplicate_count,
            "exact_duplicate_count": self.exact_duplicate_count,
            "potential_duplicate_count": self.potential_duplicate_count,
            "completeness": self.completeness.to_dict(),
            "source_health": [s.to_dict() for s in self.source_health],
            "route_health": [r.to_dict() for r in self.route_health],
            "overall_route_success_rate": self.overall_route_success_rate,
            "overall_route_coverage": self.overall_route_coverage,
        }
        if include_records:
            out["record_results"] = self.record_results
        return out
