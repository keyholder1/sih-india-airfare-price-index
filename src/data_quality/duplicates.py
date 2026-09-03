"""Duplicate detection: exact (rejected) vs. potential (flagged only).

Exact duplicates are auto-removed because, by definition, they add zero new
information (same id, or every field identical) — keeping them would double
count that fare. Potential duplicates are deliberately never auto-removed;
see docs/data_quality.md for why (near-identical fares on the same
route/date/source can legitimately be two different real quotes).
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from . import reason_codes as rc
from .config import DataQualityConfig

#: All normalized (``_dq_``-prefixed) columns, deliberately -- grouping by
#: the raw ``flight_date``/``booking_date`` strings would silently split
#: identical dates written in different formats (e.g. "2026-02-10" vs.
#: "2026-02-10T00:00:00") into different groups, so two near-identical
#: fares for the same actual date from differently-formatted sources would
#: never be compared and could never be flagged POTENTIAL_DUPLICATE.
_POTENTIAL_DUP_GROUP_COLUMNS = ["_dq_airline", "_dq_origin", "_dq_destination", "_dq_flight_date", "_dq_booking_date"]


def mark_duplicates(work: pd.DataFrame, config: DataQualityConfig) -> Tuple[pd.DataFrame, int, int]:
    """Mutates ``work`` in place (sets rejection_reason / appends flags).

    Returns ``(work, exact_duplicate_count, potential_duplicate_count)``.
    """
    exact_count = _mark_exact_duplicates(work)
    potential_count = _mark_potential_duplicates(work, config)
    return work, exact_count, potential_count


def _mark_exact_duplicates(work: pd.DataFrame) -> int:
    candidate_mask = work["rejection_reason"].isna()
    candidates = work[candidate_mask]
    if candidates.empty:
        return 0

    dup_by_id = candidates.duplicated(subset=["_dq_observation_id"], keep="first")

    non_id_cols = [c for c in candidates.columns if not c.startswith("_dq_") and c != "observation_id" and c != "rejection_reason" and c != "flag_reasons"]
    # fillna first: under pandas' string dtype, astype(str) leaves missing
    # values as NaN (a float) instead of stringifying them, which breaks
    # "|".join below and would also silently treat NaN != NaN as "not a
    # duplicate" even when every other field matches.
    content_key = candidates[non_id_cols].fillna("").astype(str).agg("|".join, axis=1)
    dup_by_content = content_key.duplicated(keep="first")

    exact_dup = (dup_by_id | dup_by_content).reindex(work.index, fill_value=False)
    work.loc[exact_dup, "rejection_reason"] = rc.EXACT_DUPLICATE
    return int(exact_dup.sum())


def _mark_potential_duplicates(work: pd.DataFrame, config: DataQualityConfig) -> int:
    candidate_mask = work["rejection_reason"].isna()
    candidates = work[candidate_mask]
    if candidates.empty:
        return 0

    group_cols = list(_POTENTIAL_DUP_GROUP_COLUMNS)
    if "source" in candidates.columns:
        group_cols.append("source")

    flagged_count = 0
    for _, group in candidates.groupby(group_cols, dropna=False):
        if len(group) < 2:
            continue
        seen_fares = []
        for idx, fare in group["_dq_fare"].items():
            if pd.isna(fare):
                continue
            is_dup = any(
                abs(fare - seen) <= config.potential_duplicate_fare_tolerance_pct * max(abs(seen), 1e-9)
                for seen in seen_fares
            )
            if is_dup:
                work.at[idx, "flag_reasons"].append(rc.POTENTIAL_DUPLICATE)
                flagged_count += 1
            seen_fares.append(fare)

    return flagged_count
