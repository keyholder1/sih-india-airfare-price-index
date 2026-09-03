"""Batch-level completeness metrics.

Distinct from validity: a record can have every required field present
(complete) and still be rejected for a bad *value* (e.g. flight_date before
booking_date), and vice versa a record missing an optional field is still
100% "complete" for scoring purposes unless configured otherwise.
"""

from __future__ import annotations

import pandas as pd

from index_engine.config import REQUIRED_COLUMNS

from .config import DataQualityConfig
from .models import CompletenessReport
from .validation import OPTIONAL_COLUMNS, blank_mask


def compute_completeness(df: pd.DataFrame, config: DataQualityConfig) -> CompletenessReport:
    total = len(df)
    if total == 0:
        return CompletenessReport(
            total_records=0,
            records_with_all_required_fields=0,
            records_missing_required_fields=0,
            records_missing_optional_fields=0,
            completeness_rate=0.0,
        )

    required_present = [c for c in REQUIRED_COLUMNS if c in df.columns]
    missing_required_mask = pd.Series(False, index=df.index)
    for col in required_present:
        missing_required_mask = missing_required_mask | blank_mask(df[col])
    # Any required column entirely absent from the schema means every row is missing it.
    if len(required_present) < len(REQUIRED_COLUMNS):
        missing_required_mask[:] = True

    records_missing_required = int(missing_required_mask.sum())
    records_with_all_required = total - records_missing_required

    present_optional = [c for c in OPTIONAL_COLUMNS if c in df.columns]
    if present_optional:
        missing_optional_mask = pd.Series(False, index=df.index)
        for col in present_optional:
            missing_optional_mask = missing_optional_mask | blank_mask(df[col])
        records_missing_optional = int(missing_optional_mask.sum())
    else:
        # No optional columns sent at all: every row lacks all optional info.
        missing_optional_mask = pd.Series(True, index=df.index)
        records_missing_optional = total

    if config.require_optional_fields_for_completeness:
        # Stricter mode: a record only counts as "complete" if it also has
        # every optional field the batch's schema carries (or, if none were
        # sent at all, no record can be complete under this mode — that is
        # the point of asking for a stricter rate).
        fully_complete_mask = ~missing_required_mask & ~missing_optional_mask
    else:
        fully_complete_mask = ~missing_required_mask

    completeness_rate = int(fully_complete_mask.sum()) / total

    return CompletenessReport(
        total_records=total,
        records_with_all_required_fields=records_with_all_required,
        records_missing_required_fields=records_missing_required,
        records_missing_optional_fields=records_missing_optional,
        completeness_rate=completeness_rate,
    )
