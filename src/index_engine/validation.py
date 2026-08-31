"""Schema validation for raw fare observations.

This is the first pipeline stage: it only checks that a record is
well-formed enough to reason about (required fields present, dates parse,
fare is numeric). Statistical cleaning (outliers, duplicates) happens later
in :mod:`index_engine.cleaning`.
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from .config import REQUIRED_COLUMNS

REASON_MISSING_COLUMN = "MISSING_REQUIRED_COLUMN"
REASON_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
REASON_INVALID_DATE = "INVALID_DATE"
REASON_INVALID_FARE = "INVALID_FARE"
REASON_SAME_ORIGIN_DESTINATION = "SAME_ORIGIN_DESTINATION"
REASON_IMPOSSIBLE_BOOKING_HORIZON = "IMPOSSIBLE_BOOKING_HORIZON"


def validate_observations(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split raw observations into structurally valid and rejected rows.

    Returns
    -------
    (valid, rejected) where ``rejected`` has the same columns as the input
    plus a ``rejection_reason`` column.
    """
    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        raise ValueError(f"Input is missing required columns: {missing_columns}")

    work = df.copy()
    work["flight_date"] = pd.to_datetime(work["flight_date"], errors="coerce")
    work["booking_date"] = pd.to_datetime(work["booking_date"], errors="coerce")
    work["total_fare"] = pd.to_numeric(work["total_fare"], errors="coerce")

    reasons = pd.Series([None] * len(work), index=work.index, dtype=object)

    required_nonnull = ["observation_id", "airline", "origin", "destination", "currency"]
    missing_required = work[required_nonnull].isna().any(axis=1) | (
        work[required_nonnull].astype(str).apply(lambda s: s.str.strip() == "").any(axis=1)
    )
    reasons[missing_required & reasons.isna()] = REASON_MISSING_REQUIRED_FIELD

    bad_date = work["flight_date"].isna() | work["booking_date"].isna()
    reasons[bad_date & reasons.isna()] = REASON_INVALID_DATE

    bad_fare = work["total_fare"].isna() | (work["total_fare"] <= 0)
    reasons[bad_fare & reasons.isna()] = REASON_INVALID_FARE

    same_od = work["origin"].astype(str).str.upper() == work["destination"].astype(str).str.upper()
    reasons[same_od & reasons.isna()] = REASON_SAME_ORIGIN_DESTINATION

    impossible_horizon = (work["flight_date"] - work["booking_date"]).dt.days < 0
    impossible_horizon = impossible_horizon.fillna(False)
    reasons[impossible_horizon & reasons.isna()] = REASON_IMPOSSIBLE_BOOKING_HORIZON

    valid_mask = reasons.isna()
    valid = work[valid_mask].copy()
    rejected = work[~valid_mask].copy()
    rejected["rejection_reason"] = reasons[~valid_mask]
    return valid, rejected
