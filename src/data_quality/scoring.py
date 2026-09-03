"""Transparent, explainable quality score.

Deliberately a documented weighted sum of five plain-English rates, not an
opaque/learned score — see docs/data_quality.md. Grade bands are explicitly
PROTOTYPE thresholds, not an official statistical standard.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .config import DataQualityConfig


def compute_quality_score(
    *,
    completeness_rate: float,
    validity_rate: float,
    duplicate_rate: float,
    schema_compliance_rate: float,
    source_success_rate: Optional[float],
    config: DataQualityConfig,
) -> Tuple[float, str]:
    """Returns ``(quality_score, quality_grade)``.

    ``source_success_rate`` is ``None`` when no ``route_attempts`` log was
    supplied to the pipeline — treated as neutral (1.0) rather than
    penalizing every batch for an optional input nobody sent.
    """
    w = config.quality_score_weights
    effective_source_success = source_success_rate if source_success_rate is not None else 1.0

    raw_score = 100.0 * (
        w.completeness * completeness_rate
        + w.validity * validity_rate
        + w.duplicate * (1.0 - duplicate_rate)
        + w.schema_compliance * schema_compliance_rate
        + w.source_success * effective_source_success
    )
    score = max(0.0, min(100.0, raw_score))

    grade = "POOR"
    for min_score, band_grade in config.quality_grade_bands:
        if score >= min_score:
            grade = band_grade
            break

    return round(score, 2), grade
