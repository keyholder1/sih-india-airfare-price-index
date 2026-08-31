"""Schema validation, field-level validation, and attention flags.

Two pipeline stages live here because both are per-row, vectorized passes
over the same working DataFrame:

1. ``validate_fields`` — REJECTION checks (record cannot safely enter the
   index pipeline). Mirrors ``index_engine.validation`` in spirit and in
   the underlying rules (missing/invalid required fields, bad dates,
   same origin/destination, impossible booking horizon, non-positive fare)
   but reports one reason code *per field* instead of one lumped
   ``MISSING_REQUIRED_FIELD``, and adds checks the engine doesn't do at all
   (airport code format, currency). The index engine still re-runs its own
   validation on whatever this layer forwards — that's intentional
   defense-in-depth, not duplication to remove.
2. ``apply_flags`` — FLAG checks (structurally valid, deserves attention).
   Nothing here rejects a record; see docs/data_quality.md for why
   suspicious-fare detection is deliberately *not* the same thing as the
   index engine's statistical outlier detection.

Only rows that survived stage 1 (``rejection_reason`` is still None) are
considered for stage 2 and for duplicate detection (duplicates.py).
"""

from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from index_engine.config import REQUIRED_COLUMNS

from . import reason_codes as rc
from .config import DataQualityConfig
from .reference_data import KNOWN_AIRLINES, KNOWN_AIRPORTS

OPTIONAL_COLUMNS: Tuple[str, ...] = (
    "timestamp",
    "source",
    "fare_class",
    "fare_type",
    "base_fare",
    "taxes",
    "fees",
    "stops",
    "duration",
    "baggage",
    "availability",
)

_IATA_FORMAT = r"^[A-Z]{3}$"


def check_schema(df: pd.DataFrame) -> List[str]:
    """Return the list of required columns missing from ``df`` (empty if OK)."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def blank_mask(series: pd.Series) -> pd.Series:
    """True where a value is null/NaN or, once stringified, blank."""
    return series.isna() | (series.fillna("").astype(str).str.strip() == "")


def prepare_working_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Attach normalized/coerced helper columns used by every later stage.

    Helper columns are prefixed ``_dq_`` so they can never collide with a
    real scraper field and are easy to strip before handing rows back.
    """
    work = df.copy()
    work["_dq_flight_date"] = pd.to_datetime(work["flight_date"], errors="coerce", format="mixed")
    work["_dq_booking_date"] = pd.to_datetime(work["booking_date"], errors="coerce", format="mixed")
    work["_dq_fare"] = pd.to_numeric(work["total_fare"], errors="coerce")
    work["_dq_origin"] = work["origin"].fillna("").astype(str).str.strip().str.upper()
    work["_dq_destination"] = work["destination"].fillna("").astype(str).str.strip().str.upper()
    work["_dq_currency"] = work["currency"].fillna("").astype(str).str.strip().str.upper()
    work["_dq_airline"] = work["airline"].fillna("").astype(str).str.strip()
    work["_dq_observation_id"] = work["observation_id"].fillna("").astype(str).str.strip()
    work["_dq_route"] = work["_dq_origin"] + "-" + work["_dq_destination"]
    work["_dq_horizon_days"] = (work["_dq_flight_date"] - work["_dq_booking_date"]).dt.days
    work["rejection_reason"] = pd.Series([None] * len(work), index=work.index, dtype=object)
    work["flag_reasons"] = [[] for _ in range(len(work))]
    return work


def validate_fields(work: pd.DataFrame, config: DataQualityConfig) -> pd.DataFrame:
    """Fill in ``work["rejection_reason"]`` in place; returns ``work``.

    First matching rule wins (a row gets exactly one rejection reason, the
    same "don't pile on" convention as index_engine.validation), checked in
    this order: identity fields, route validity, dates, currency, fare.
    """
    reasons = work["rejection_reason"]

    def assign(mask: pd.Series, code: str) -> None:
        open_mask = mask.fillna(False) & reasons.isna()
        reasons[open_mask] = code

    assign(blank_mask(work["observation_id"]), rc.MISSING_OBSERVATION_ID)
    assign(blank_mask(work["airline"]), rc.MISSING_AIRLINE)
    assign(blank_mask(work["origin"]), rc.MISSING_ORIGIN)
    assign(blank_mask(work["destination"]), rc.MISSING_DESTINATION)

    bad_origin_format = ~work["_dq_origin"].str.match(_IATA_FORMAT, na=False)
    bad_destination_format = ~work["_dq_destination"].str.match(_IATA_FORMAT, na=False)
    assign(bad_origin_format | bad_destination_format, rc.INVALID_AIRPORT_CODE)

    assign(work["_dq_origin"] == work["_dq_destination"], rc.SAME_ORIGIN_DESTINATION)

    assign(work["_dq_flight_date"].isna(), rc.INVALID_FLIGHT_DATE)
    assign(work["_dq_booking_date"].isna(), rc.INVALID_BOOKING_DATE)
    assign(work["_dq_horizon_days"] < 0, rc.NEGATIVE_BOOKING_HORIZON)

    assign(blank_mask(work["currency"]), rc.MISSING_CURRENCY)
    non_inr = ~work["_dq_currency"].isin(config.allowed_currencies) & ~blank_mask(work["currency"])
    assign(non_inr, rc.NON_INR_CURRENCY)

    bad_fare = work["_dq_fare"].isna() | (work["_dq_fare"] <= 0)
    assign(bad_fare, rc.NON_POSITIVE_FARE)

    work["rejection_reason"] = reasons
    return work


def _suspicious_fare_mask(work: pd.DataFrame, config: DataQualityConfig) -> pd.Series:
    """Coarse, explainable relative sanity check — NOT the index engine's
    statistical outlier test (see module docstring). Robust (median/MAD)
    per-route, falling back to the whole batch when a route has too few
    points to say anything meaningful. Rows where no group ever reaches the
    minimum size are simply never flagged (documented limitation)."""
    candidates = work[work["rejection_reason"].isna()]
    flags = pd.Series(False, index=work.index)
    if candidates.empty:
        return flags

    def mad_bounds(fares: pd.Series):
        median = fares.median()
        mad = (fares - median).abs().median()
        if mad == 0:
            return None
        scaled_mad = 1.4826 * mad
        margin = config.fare_sanity_mad_multiplier * scaled_mad
        return median - margin, median + margin

    batch_bounds = None
    if len(candidates) >= config.fare_sanity_group_min_size:
        batch_bounds = mad_bounds(candidates["_dq_fare"].dropna())

    for _, group in candidates.groupby("_dq_route"):
        fares = group["_dq_fare"].dropna()
        bounds = mad_bounds(fares) if len(fares) >= config.fare_sanity_group_min_size else batch_bounds
        if bounds is None:
            continue
        lower, upper = bounds
        group_flags = (group["_dq_fare"] < lower) | (group["_dq_fare"] > upper)
        flags.loc[group_flags[group_flags.fillna(False)].index] = True

    return flags


def apply_flags(work: pd.DataFrame, config: DataQualityConfig, reference_time: pd.Timestamp | None = None) -> pd.DataFrame:
    """Append flag codes to ``work["flag_reasons"]`` for structurally-valid
    rows (``rejection_reason`` is None). Multiple flags can apply to one
    row — unlike rejection, these are additive attention markers, not
    mutually exclusive outcomes."""
    candidate_mask = work["rejection_reason"].isna()

    def add_flag(mask: pd.Series, code: str) -> None:
        for idx in work.index[mask.fillna(False) & candidate_mask]:
            work.at[idx, "flag_reasons"].append(code)

    add_flag(_suspicious_fare_mask(work, config), rc.SUSPICIOUS_FARE)

    unmapped = ~work["_dq_origin"].isin(KNOWN_AIRPORTS) | ~work["_dq_destination"].isin(KNOWN_AIRPORTS)
    add_flag(unmapped, rc.UNMAPPED_LOCATION)

    unknown_airline = ~work["_dq_airline"].str.upper().isin(KNOWN_AIRLINES)
    add_flag(unknown_airline, rc.UNKNOWN_AIRLINE)

    present_optional = [c for c in OPTIONAL_COLUMNS if c in work.columns]
    if present_optional:
        missing_optional = pd.Series(False, index=work.index)
        for col in present_optional:
            missing_optional = missing_optional | blank_mask(work[col])
        add_flag(missing_optional, rc.MISSING_OPTIONAL_FIELD)

    if "timestamp" in work.columns:
        ts = pd.to_datetime(work["timestamp"], errors="coerce", format="mixed")
        ref = reference_time if reference_time is not None else ts.max()
        if ref is not None and pd.notna(ref):
            max_age = pd.Timedelta(config.stale_observation_max_age)
            age = ref - ts
            stale = age.notna() & (age > max_age)
            add_flag(stale, rc.STALE_OBSERVATION)

    unusual_horizon = work["_dq_horizon_days"] > config.unusual_booking_horizon_days
    add_flag(unusual_horizon, rc.UNUSUAL_BOOKING_HORIZON)

    return work
