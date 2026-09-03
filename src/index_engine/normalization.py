"""Fare standardization: derive comparable fields from raw observations.

Everything here is deterministic feature-derivation (route, period, booking
horizon bucket, standardized fare) — no statistics yet. That happens in
:mod:`index_engine.aggregation`.
"""

from __future__ import annotations

import pandas as pd

from .config import BOOKING_HORIZON_BUCKETS, IndexConfig


def add_route(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["route"] = df["origin"].astype(str).str.upper() + "-" + df["destination"].astype(str).str.upper()
    return df


def add_period(df: pd.DataFrame) -> pd.DataFrame:
    """Assign each observation to a year-month period based on flight_date.

    The index tracks the price of *flying in a given month*, not the price
    of *booking in a given month* — so the period key is the travel date,
    consistent with how a consumer price index dates a purchase by when the
    good/service is consumed.
    """
    df = df.copy()
    df["period"] = pd.to_datetime(df["flight_date"]).dt.strftime("%Y-%m")
    return df


def add_booking_horizon(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    horizon_days = (pd.to_datetime(df["flight_date"]) - pd.to_datetime(df["booking_date"])).dt.days
    df["booking_horizon_days"] = horizon_days

    def bucket_for(days: float) -> str:
        for label, low, high in BOOKING_HORIZON_BUCKETS:
            if high is None:
                if days >= low:
                    return label
            elif low <= days <= high:
                return label
        return "unknown"

    df["booking_horizon_bucket"] = horizon_days.apply(bucket_for)
    return df


def add_standardized_fare(df: pd.DataFrame, config: IndexConfig) -> pd.DataFrame:
    """Attach the ``standardized_fare`` column used by every downstream step.

    Standardized fare definition (prototype default): total mandatory
    payable one-way fare for one adult passenger, including mandatory taxes
    and fees, excluding optional add-ons (baggage, seat selection,
    insurance). This is controlled by ``config.fare_field`` so a different
    definition can be swapped in without touching any other module.
    """
    df = df.copy()
    if config.fare_field not in df.columns:
        raise ValueError(f"fare_field {config.fare_field!r} not present in observations")
    df["standardized_fare"] = pd.to_numeric(df[config.fare_field], errors="coerce")
    return df


def enrich(df: pd.DataFrame, config: IndexConfig) -> pd.DataFrame:
    """Run all normalization steps in the correct order."""
    df = add_route(df)
    df = add_period(df)
    df = add_booking_horizon(df)
    df = add_standardized_fare(df, config)
    return df
