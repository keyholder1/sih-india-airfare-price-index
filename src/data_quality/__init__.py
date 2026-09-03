"""Data Quality / Validation layer — sits between the scraper and the
index engine.

    from data_quality import validate_fare_batch

    quality_result = validate_fare_batch(raw_observations)
    clean_data = quality_result.valid_observations

    engine = AirfarePriceIndex(base_period="2026-01")
    index_result = engine.calculate(observations=clean_data, current_period="2026-08")

See docs/data_quality.md for the full pipeline, reason codes, and the
(deliberate) separation between this module's SUSPICIOUS_FARE flag and the
index engine's own statistical outlier detection.
"""

from .config import DataQualityConfig, QualityScoreWeights
from .models import CompletenessReport, DataQualityResult, RouteHealth, SourceHealth
from .pipeline import validate_fare_batch
from .reason_codes import (
    FLAG_REASONS,
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_HEALTHY,
    HEALTH_UNKNOWN,
    REJECTION_REASONS,
    STATUS_FLAGGED,
    STATUS_REJECTED,
    STATUS_VALID,
)

__all__ = [
    "validate_fare_batch",
    "DataQualityConfig",
    "QualityScoreWeights",
    "DataQualityResult",
    "CompletenessReport",
    "SourceHealth",
    "RouteHealth",
    "REJECTION_REASONS",
    "FLAG_REASONS",
    "STATUS_VALID",
    "STATUS_FLAGGED",
    "STATUS_REJECTED",
    "HEALTH_HEALTHY",
    "HEALTH_DEGRADED",
    "HEALTH_FAILED",
    "HEALTH_UNKNOWN",
]

__version__ = "0.1.0"
