"""Route weighting.

Weights determine how much each route's price movement counts toward the
national index. They are deliberately kept external and swappable: nothing
in this file should ever be presented as an official government weight.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

WEIGHT_COLUMNS = ("origin", "destination", "weight", "effective_from", "effective_to", "source")


def validate_weights(weights: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ("origin", "destination", "weight") if c not in weights.columns]
    if missing:
        raise ValueError(f"Weights table is missing required columns: {missing}")
    w = weights.copy()
    w["origin"] = w["origin"].astype(str).str.upper()
    w["destination"] = w["destination"].astype(str).str.upper()
    w["route"] = w["origin"] + "-" + w["destination"]
    if "effective_from" not in w.columns:
        w["effective_from"] = None
    if "effective_to" not in w.columns:
        w["effective_to"] = None
    if "source" not in w.columns:
        w["source"] = "UNSPECIFIED"
    return w


def weights_for_period(weights: pd.DataFrame, period: str) -> pd.DataFrame:
    """Select the weight row effective for a given ``YYYY-MM`` period."""
    w = validate_weights(weights)
    period_ts = pd.to_datetime(period)
    from_ok = w["effective_from"].isna() | (pd.to_datetime(w["effective_from"]) <= period_ts)
    to_ok = w["effective_to"].isna() | (pd.to_datetime(w["effective_to"]) >= period_ts)
    return w[from_ok & to_ok]


def normalize_weights(weights: pd.DataFrame) -> pd.DataFrame:
    """Rescale weights so they sum to 1 (per selected period)."""
    w = weights.copy()
    total = w["weight"].sum()
    w["weight_normalized"] = w["weight"] / total if total else 0.0
    return w


def generate_synthetic_weights(routes: Iterable[str], source: str = "SYNTHETIC_DEMO_ONLY") -> pd.DataFrame:
    """Build illustrative, clearly-labelled weights for prototype/demo use.

    THESE ARE NOT REAL PASSENGER-VOLUME OR OFFICIAL CPI WEIGHTS. They exist
    only so the pipeline is runnable end-to-end before the team has real
    weight data. Metro-to-metro trunk routes are given a higher illustrative
    weight than others, loosely modelling (without citing) the intuition
    that busier routes should matter more to a national index — replace
    this entirely once real passenger-volume or expenditure weights are
    available.
    """
    metros = {"DEL", "BOM", "BLR", "MAA", "CCU", "HYD"}
    rows = []
    for route in routes:
        origin, destination = route.split("-")
        both_metro = origin in metros and destination in metros
        weight = 3.0 if both_metro else 1.0
        rows.append(
            {
                "origin": origin,
                "destination": destination,
                "weight": weight,
                "effective_from": None,
                "effective_to": None,
                "source": source,
            }
        )
    return pd.DataFrame(rows)
