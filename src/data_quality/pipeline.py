"""Public entry point: :func:`validate_fare_batch`.

Pipeline (see docs/data_quality.md for the full rationale of each step):

    raw scraper output
        -> schema validation      (are the required columns even present?)
        -> field validation       (per-row REJECTION checks, one reason each)
        -> duplicate detection    (exact -> rejected, potential -> flagged)
        -> attention flags        (suspicious fare, unmapped city, ...)
        -> completeness scoring
        -> source health / route health
        -> quality score + grade
        -> DataQualityResult (valid_observations ready for AirfarePriceIndex)

Nothing is silently dropped: every input row ends up VALID, FLAGGED, or
REJECTED (with a reason), and that outcome is recoverable per-row from
``DataQualityResult.record_results``.
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

import pandas as pd

from . import reason_codes as rc
from .completeness import compute_completeness
from .config import DataQualityConfig
from .duplicates import mark_duplicates
from .health import (
    RouteAttempts,
    compute_route_health,
    compute_source_health,
    overall_route_coverage,
    overall_route_success_rate,
)
from .models import DataQualityResult
from .scoring import compute_quality_score
from .validation import check_schema, prepare_working_frame, validate_fields, apply_flags

_HELPER_COLUMN_PREFIX = "_dq_"


def validate_fare_batch(
    raw_data: Union[pd.DataFrame, Sequence[dict]],
    route_attempts: Optional[RouteAttempts] = None,
    config: Optional[DataQualityConfig] = None,
    reference_time: Optional[pd.Timestamp] = None,
    base_period: Optional[str] = None,
    current_period: Optional[str] = None,
) -> DataQualityResult:
    """Validate a batch of raw fare observations before they reach the index engine.

    Parameters
    ----------
    raw_data:
        A DataFrame or list of dicts, one row per fare observation — same
        shape as what ``AirfarePriceIndex.calculate`` eventually expects
        (see docs/data_contract.md).
    route_attempts:
        Optional scraper request log (see health.py docstring) enabling
        ``routes_requested``/``routes_successful``/route coverage metrics.
        Omit if the scraper doesn't track this yet — everything else still
        works, just with those specific fields left as ``None``.
    config:
        Optional :class:`DataQualityConfig`; defaults are documented
        prototype thresholds.
    reference_time:
        Clock to measure staleness/freshness against. Defaults to "now";
        pass an explicit timestamp for deterministic tests/backtests.
    base_period, current_period:
        Optional ``YYYY-MM`` periods, purely to populate
        ``RouteHealth.has_base_period_data`` / ``has_current_period_data``.
        Not required — everything else in the result is period-agnostic.
    """
    config = config or DataQualityConfig()
    df = _to_dataframe(raw_data)
    total_received = len(df)

    missing_columns = check_schema(df)
    if missing_columns:
        return _schema_failure_result(df, missing_columns, config)

    work = prepare_working_frame(df)
    work = validate_fields(work, config)
    work, exact_dup_count, potential_dup_count = mark_duplicates(work, config)
    work = apply_flags(work, config, reference_time=reference_time)

    work["status"] = _classify_status(work)

    records_valid = int((work["status"] == rc.STATUS_VALID).sum())
    records_flagged = int((work["status"] == rc.STATUS_FLAGGED).sum())
    records_rejected = int((work["status"] == rc.STATUS_REJECTED).sum())

    completeness = compute_completeness(df, config)

    rejection_reasons = (
        work.loc[work["status"] == rc.STATUS_REJECTED, "rejection_reason"].value_counts().to_dict()
    )
    flag_reasons = _count_flags(work)

    validity_rate = records_valid / total_received if total_received else 0.0
    duplicate_rate = exact_dup_count / total_received if total_received else 0.0
    schema_compliance_rate = 1.0

    source_health = compute_source_health(work, route_attempts, config, reference_time=reference_time)
    route_health = compute_route_health(work, config, base_period=base_period, current_period=current_period)

    route_success = overall_route_success_rate(source_health)
    observed_routes = set(work.loc[work["status"] != rc.STATUS_REJECTED, "_dq_route"])
    route_coverage = overall_route_coverage(route_attempts, observed_routes)

    quality_score, quality_grade = compute_quality_score(
        completeness_rate=completeness.completeness_rate,
        validity_rate=validity_rate,
        duplicate_rate=duplicate_rate,
        schema_compliance_rate=schema_compliance_rate,
        source_success_rate=route_success,
        config=config,
    )

    passthrough_mask = work["status"] != rc.STATUS_REJECTED
    valid_observations = df.loc[passthrough_mask].to_dict("records")

    record_results = [
        {
            "row_index": int(idx),
            "observation_id": row.get("observation_id"),
            "status": row["status"],
            "rejection_reason": row["rejection_reason"],
            "flag_reasons": list(row["flag_reasons"]),
        }
        for idx, row in zip(work.index, work.to_dict("records"))
    ]

    return DataQualityResult(
        records_received=total_received,
        records_valid=records_valid,
        records_flagged=records_flagged,
        records_rejected=records_rejected,
        completeness_rate=completeness.completeness_rate,
        validity_rate=validity_rate,
        duplicate_rate=duplicate_rate,
        quality_score=quality_score,
        quality_grade=quality_grade,
        rejection_reasons=rejection_reasons,
        flag_reasons=flag_reasons,
        duplicate_count=exact_dup_count + potential_dup_count,
        exact_duplicate_count=exact_dup_count,
        potential_duplicate_count=potential_dup_count,
        completeness=completeness,
        source_health=source_health,
        route_health=route_health,
        valid_observations=valid_observations,
        overall_route_success_rate=route_success,
        overall_route_coverage=route_coverage,
        record_results=record_results,
    )


def _classify_status(work: pd.DataFrame) -> pd.Series:
    rejected = work["rejection_reason"].notna()
    flagged = work["flag_reasons"].apply(len) > 0
    status = pd.Series(rc.STATUS_VALID, index=work.index, dtype=object)
    status[flagged] = rc.STATUS_FLAGGED
    status[rejected] = rc.STATUS_REJECTED
    return status


def _count_flags(work: pd.DataFrame) -> dict:
    counts: dict = {}
    for flags in work["flag_reasons"]:
        for f in flags:
            counts[f] = counts.get(f, 0) + 1
    return counts


def _schema_failure_result(df: pd.DataFrame, missing_columns: list, config: DataQualityConfig) -> DataQualityResult:
    """The batch is missing required columns entirely — every row is
    unusable, but still accounted for (never silently dropped)."""
    total = len(df)
    completeness = compute_completeness(df, config)
    quality_score, quality_grade = compute_quality_score(
        completeness_rate=0.0,
        validity_rate=0.0,
        duplicate_rate=0.0,
        schema_compliance_rate=0.0,
        source_success_rate=None,
        config=config,
    )
    record_results = [
        {
            "row_index": int(idx),
            "observation_id": row.get("observation_id"),
            "status": rc.STATUS_REJECTED,
            "rejection_reason": rc.INVALID_SCHEMA,
            "flag_reasons": [],
        }
        for idx, row in zip(df.index, df.to_dict("records"))
    ]
    return DataQualityResult(
        records_received=total,
        records_valid=0,
        records_flagged=0,
        records_rejected=total,
        completeness_rate=0.0,
        validity_rate=0.0,
        duplicate_rate=0.0,
        quality_score=quality_score,
        quality_grade=quality_grade,
        rejection_reasons={rc.INVALID_SCHEMA: total} if total else {},
        flag_reasons={},
        duplicate_count=0,
        exact_duplicate_count=0,
        potential_duplicate_count=0,
        completeness=completeness,
        source_health=[],
        route_health=[],
        valid_observations=[],
        overall_route_success_rate=None,
        overall_route_coverage=None,
        record_results=record_results,
    )


def _to_dataframe(raw_data: Union[pd.DataFrame, Sequence[dict]]) -> pd.DataFrame:
    if isinstance(raw_data, pd.DataFrame):
        return raw_data.reset_index(drop=True).copy()
    return pd.DataFrame(list(raw_data))
