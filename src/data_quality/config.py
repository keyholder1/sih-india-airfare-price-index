"""Configuration for the data quality layer.

Every tunable check lives here rather than hard-coded inline, in the same
spirit as ``index_engine.config.IndexConfig``. Nothing in this file is an
"official" statistical standard — these are prototype monitoring defaults,
documented as such; see docs/data_quality.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple

from .reference_data import ALLOWED_CURRENCIES


@dataclass
class QualityScoreWeights:
    """Weights for the transparent, explainable quality score (0-100).

    Must sum to 1.0. ``source_success`` falls back to a neutral 1.0 input
    (not 0) when no ``route_attempts`` log was supplied, so the absence of
    that optional input doesn't tank the score — see health.py.
    """

    completeness: float = 0.25
    validity: float = 0.35
    duplicate: float = 0.15
    schema_compliance: float = 0.10
    source_success: float = 0.15

    def __post_init__(self) -> None:
        total = self.completeness + self.validity + self.duplicate + self.schema_compliance + self.source_success
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"QualityScoreWeights must sum to 1.0, got {total}")


#: (min_score_inclusive, grade) pairs, highest first. PROTOTYPE thresholds
#: only — not an official statistical standard. See docs/data_quality.md.
QUALITY_GRADE_BANDS: Tuple[Tuple[float, str], ...] = (
    (95.0, "EXCELLENT"),
    (90.0, "GOOD"),
    (75.0, "WARNING"),
    (0.0, "POOR"),
)


@dataclass
class DataQualityConfig:
    """All tunable thresholds for the data quality pipeline.

    fare_sanity_group_min_size / fare_sanity_mad_multiplier:
        SUSPICIOUS_FARE is a coarse, relative sanity net over the raw
        batch (median absolute deviation per route, falling back to the
        whole batch when a route doesn't have enough points) — deliberately
        much wider than the index engine's own outlier detector
        (``IndexConfig.outlier_mad_threshold`` etc.), because this layer's
        job is to catch obvious scraping errors, not to make the
        statistical outlier call. See docs/data_quality.md §8.
    potential_duplicate_fare_tolerance_pct:
        Two same-route/same-date/same-source observations with fares within
        this fraction of each other are flagged POTENTIAL_DUPLICATE (never
        auto-rejected — see docs/data_quality.md §duplicate-handling).
    unusual_booking_horizon_days:
        Booking horizons beyond this many days are legitimate but rare
        enough to flag for a human to sanity-check (not reject).
    stale_observation_max_age:
        pandas Timedelta-parseable string. An observation whose ``timestamp``
        is older than this, relative to ``reference_time`` (or the newest
        timestamp in the batch if none given), is flagged STALE_OBSERVATION.
    degraded_validity_rate_threshold / degraded_route_success_rate_threshold:
        Below these, a source's scraper_health status becomes DEGRADED
        (see health.py). A source with zero observations is FAILED
        regardless of these thresholds.
    """

    allowed_currencies: FrozenSet[str] = field(default_factory=lambda: ALLOWED_CURRENCIES)
    require_optional_fields_for_completeness: bool = False

    fare_sanity_group_min_size: int = 5
    fare_sanity_mad_multiplier: float = 6.0

    potential_duplicate_fare_tolerance_pct: float = 0.01
    unusual_booking_horizon_days: int = 330
    stale_observation_max_age: str = "14D"

    degraded_validity_rate_threshold: float = 0.85
    degraded_route_success_rate_threshold: float = 0.80

    quality_score_weights: QualityScoreWeights = field(default_factory=QualityScoreWeights)
    quality_grade_bands: Tuple[Tuple[float, str], ...] = QUALITY_GRADE_BANDS

    def __post_init__(self) -> None:
        if self.fare_sanity_group_min_size < 2:
            raise ValueError("fare_sanity_group_min_size must be >= 2")
        if not 0 < self.potential_duplicate_fare_tolerance_pct < 1:
            raise ValueError("potential_duplicate_fare_tolerance_pct must be in (0, 1)")
        if not self.allowed_currencies:
            raise ValueError("allowed_currencies must not be empty")
