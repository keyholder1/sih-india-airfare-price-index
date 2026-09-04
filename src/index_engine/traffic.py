"""DGCA passenger-traffic ingestion and route-importance weight calculation.

These are **route-importance weights derived from DGCA domestic passenger
traffic**, not official CPI expenditure weights and not an official
statistic in their own right — see docs/methodology.md for the full
disclaimer. This module only computes a weighting input; it does not
touch the core index calculation in index_engine.index, which is
unchanged and still just consumes an (origin, destination, weight)
DataFrame regardless of where the weight came from.

Pipeline:

    raw DGCA CSV (Year, Month, City1, City2, PaxToCity2, PaxFromCity2)
        -> validate_traffic          (reasons recorded, nothing silently dropped)
        -> to_directional            (wide, two-directions-per-row -> long, one direction per row)
        -> aggregate_period          (sum passengers per route over a period window)
        -> national_weights          (route passengers / ALL eligible domestic passengers)
        -> covered_subset            (restrict to routes we have airfare data for, renormalize)
        -> to_engine_weights         (IATA codes, ready for AirfarePriceIndex(weights=...))
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import pandas as pd

from .city_mapping import city_to_iata, iata_to_city

REQUIRED_TRAFFIC_COLUMNS = ("Year", "Month", "City1", "City2", "PaxToCity2", "PaxFromCity2")

REASON_MISSING_CITY = "MISSING_CITY"
REASON_SAME_CITY = "SAME_ORIGIN_DESTINATION"
REASON_INVALID_MONTH = "INVALID_MONTH"
REASON_INVALID_YEAR = "INVALID_YEAR"
REASON_INVALID_PASSENGERS = "INVALID_PASSENGER_COUNT"
REASON_DUPLICATE = "DUPLICATE_TRAFFIC_RECORD"

DGCA_DERIVED_SOURCE = "DGCA_DERIVED"


def load_dgca_traffic(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def validate_traffic(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Structural validation. Returns (valid, rejected-with-reason)."""
    missing_cols = [c for c in REQUIRED_TRAFFIC_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Traffic data is missing required columns: {missing_cols}")

    work = df.copy()
    work["Year"] = pd.to_numeric(work["Year"], errors="coerce")
    work["Month"] = pd.to_numeric(work["Month"], errors="coerce")
    work["PaxToCity2"] = pd.to_numeric(work["PaxToCity2"], errors="coerce")
    work["PaxFromCity2"] = pd.to_numeric(work["PaxFromCity2"], errors="coerce")
    work["City1"] = work["City1"].astype(str).str.strip().str.upper()
    work["City2"] = work["City2"].astype(str).str.strip().str.upper()

    reasons = pd.Series([None] * len(work), index=work.index, dtype=object)

    missing_city = work["City1"].isin(["", "NAN", "NONE"]) | work["City2"].isin(["", "NAN", "NONE"])
    reasons[missing_city & reasons.isna()] = REASON_MISSING_CITY

    same_city = work["City1"] == work["City2"]
    reasons[same_city & reasons.isna()] = REASON_SAME_CITY

    bad_month = work["Month"].isna() | (work["Month"] < 1) | (work["Month"] > 12)
    reasons[bad_month & reasons.isna()] = REASON_INVALID_MONTH

    bad_year = work["Year"].isna() | (work["Year"] < 1990) | (work["Year"] > 2100)
    reasons[bad_year & reasons.isna()] = REASON_INVALID_YEAR

    # Conservative: reject the whole record if either direction's passenger
    # count is missing/negative, rather than guessing which half is salvageable.
    bad_pax = (
        work["PaxToCity2"].isna() | (work["PaxToCity2"] < 0) | work["PaxFromCity2"].isna() | (work["PaxFromCity2"] < 0)
    )
    reasons[bad_pax & reasons.isna()] = REASON_INVALID_PASSENGERS

    valid_mask = reasons.isna()
    valid = work[valid_mask].copy()
    rejected = work[~valid_mask].copy()
    rejected["rejection_reason"] = reasons[~valid_mask]

    is_dup = valid.duplicated(subset=["Year", "Month", "City1", "City2"], keep="first")
    if is_dup.any():
        dup_rows = valid[is_dup].copy()
        dup_rows["rejection_reason"] = REASON_DUPLICATE
        rejected = pd.concat([rejected, dup_rows], ignore_index=True)
        valid = valid[~is_dup].copy()

    return valid, rejected


def to_directional(valid: pd.DataFrame, source: str) -> pd.DataFrame:
    """Wide (one row, two directions) -> long (one row per direction)."""
    valid = valid.copy()
    valid["period"] = valid["Year"].astype(int).astype(str).str.zfill(4) + "-" + valid["Month"].astype(int).astype(str).str.zfill(2)

    forward = valid.rename(columns={"City1": "origin", "City2": "destination", "PaxToCity2": "passengers"})[
        ["period", "origin", "destination", "passengers"]
    ]
    backward = valid.rename(columns={"City2": "origin", "City1": "destination", "PaxFromCity2": "passengers"})[
        ["period", "origin", "destination", "passengers"]
    ]
    long_df = pd.concat([forward, backward], ignore_index=True)
    long_df["source"] = source
    return long_df


def latest_available_period(long_df: pd.DataFrame) -> str:
    """Most recent period present in the traffic data — never hard-coded."""
    return long_df["period"].max()


def rolling_window(end_period: str, months: int = 12) -> Tuple[str, str]:
    """(start, end) inclusive period strings for an N-month window ending at end_period."""
    end_ts = pd.Timestamp(end_period + "-01")
    start_ts = end_ts - pd.DateOffset(months=months - 1)
    return start_ts.strftime("%Y-%m"), end_period


def aggregate_period(long_df: pd.DataFrame, start_period: str, end_period: str) -> pd.DataFrame:
    """Sum passengers per (origin, destination) over [start_period, end_period] inclusive."""
    window = long_df[(long_df["period"] >= start_period) & (long_df["period"] <= end_period)]
    aggregated = window.groupby(["origin", "destination"], as_index=False)["passengers"].sum()
    return aggregated


def national_weights(route_passengers: pd.DataFrame) -> pd.DataFrame:
    """Route passengers / ALL eligible domestic passengers in the same window.

    This is a national-network-wide total, not restricted to routes we
    happen to have airfare data for — that's what makes the resulting
    weight meaningful as "this route's share of India's domestic traffic."
    """
    total = route_passengers["passengers"].sum()
    result = route_passengers.copy()
    result["national_weight"] = result["passengers"] / total if total else 0.0
    return result


def covered_subset(national_weights_df: pd.DataFrame, covered_city_routes: Iterable[Tuple[str, str]]) -> pd.DataFrame:
    """Restrict to routes we actually have airfare data for, and renormalize.

    Returns columns: origin, destination, passengers, national_weight,
    covered_normalized_weight. The sum of national_weight in the returned
    frame IS the traffic_weight_coverage metric — see traffic_weight_coverage().
    """
    covered_set = set(covered_city_routes)
    mask = national_weights_df.apply(lambda r: (r["origin"], r["destination"]) in covered_set, axis=1)
    covered = national_weights_df[mask].copy()
    total_covered = covered["national_weight"].sum()
    covered["covered_normalized_weight"] = covered["national_weight"] / total_covered if total_covered else 0.0
    return covered


def traffic_weight_coverage(covered_df: pd.DataFrame) -> float:
    """Fraction of India's total domestic passenger traffic represented by
    the routes we have usable airfare observations for."""
    return float(covered_df["national_weight"].sum())


def to_engine_weights(
    covered_df: pd.DataFrame,
    weight_period_start: str,
    weight_period_end: str,
    source: str = DGCA_DERIVED_SOURCE,
) -> pd.DataFrame:
    """Convert covered_df (city names) into the schema AirfarePriceIndex expects
    (IATA codes): origin, destination, weight, effective_from, effective_to, source.

    ``weight`` here is the covered-route renormalized weight, NOT the raw
    national weight — see docs/methodology.md for why that distinction matters.
    Routes whose city name has no verified IATA mapping are dropped (with a
    KeyError surfaced immediately, not silently) rather than guessed.

    ``effective_from``/``effective_to`` are left open (``None``) rather than
    pinned to the traffic measurement window: those two columns mean "when
    is this weight row *in force* for index calculations," not "when was
    the underlying traffic measured." A rolling-12-month weight computed
    from mid-2025 data is still the best available weight for pricing
    periods well after that window (official traffic statistics lag several
    months behind the current calendar month) until it is recomputed with a
    newer window. The measurement window itself is preserved separately as
    ``weight_period_start``/``weight_period_end`` for provenance/reporting.
    """
    rows = []
    for _, row in covered_df.iterrows():
        rows.append(
            {
                "origin": city_to_iata(row["origin"]),
                "destination": city_to_iata(row["destination"]),
                "weight": row["covered_normalized_weight"],
                "national_weight": row["national_weight"],
                "effective_from": None,
                "effective_to": None,
                "weight_period_start": weight_period_start,
                "weight_period_end": weight_period_end,
                "source": source,
            }
        )
    return pd.DataFrame(rows)


def build_dgca_weights(
    csv_path: str,
    covered_iata_routes: Iterable[Tuple[str, str]],
    months: int = 12,
    end_period: Optional[str] = None,
) -> Tuple[pd.DataFrame, dict]:
    """End-to-end convenience wrapper: CSV path + covered IATA routes -> engine-ready weights.

    Returns (engine_weights_df, diagnostics) where diagnostics contains
    weight_period_start/end, total_routes_in_window, traffic_weight_coverage,
    and the validation/cleaning counts.
    """
    raw = load_dgca_traffic(csv_path)
    valid, rejected = validate_traffic(raw)
    long_df = to_directional(valid, source="DGCA")

    end_period = end_period or latest_available_period(long_df)
    start_period, end_period = rolling_window(end_period, months=months)

    route_passengers = aggregate_period(long_df, start_period, end_period)
    national = national_weights(route_passengers)

    # A route with no verified IATA<->city mapping (e.g. a code a user
    # typed into the on-demand pipeline that isn't in the curated
    # city_mapping table yet) must not take down weighting for every
    # OTHER route -- it degrades on its own (no DGCA weight, same as any
    # route DGCA has no traffic data for), not the whole batch. Previously
    # a single unmapped code raised here and the caller's blanket
    # except-Exception fallback silently replaced every route's real
    # weight with synthetic equal-weighting.
    covered_city_routes = []
    skipped_unmapped_routes: List[str] = []
    for o, d in covered_iata_routes:
        try:
            covered_city_routes.append((iata_to_city(o), iata_to_city(d)))
        except KeyError:
            skipped_unmapped_routes.append(f"{o}-{d}")

    covered = covered_subset(national, covered_city_routes)
    coverage = traffic_weight_coverage(covered)

    engine_weights = to_engine_weights(covered, start_period, end_period)

    diagnostics = {
        "weight_period_start": start_period,
        "weight_period_end": end_period,
        "total_routes_in_window": int(national.shape[0]),
        "total_passengers_in_window": float(national["passengers"].sum()),
        "covered_routes": int(covered.shape[0]),
        "traffic_weight_coverage": coverage,
        "records_received": int(len(raw)),
        "records_rejected": int(len(rejected)),
        "rejection_reasons": rejected["rejection_reason"].value_counts().to_dict() if len(rejected) else {},
        "skipped_unmapped_routes": skipped_unmapped_routes,
    }
    return engine_weights, diagnostics
