"""Representative-fare computation and national index aggregation.

Two distinct statistical steps live here:

1. Collapsing many observations for a (route, period) into one representative
   fare (:func:`representative_fare`, :func:`compute_route_period_fares`).
2. Combining many route-level indices into one national index
   (:func:`national_index`).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import stats as _stats  # only used for trimmed mean

from .config import IndexConfig
from .models import RouteIndexResult


def representative_fare(fares: pd.Series, config: IndexConfig) -> Optional[float]:
    """Collapse a set of standardized fares into one representative value.

    Defaults to the median: airfares are strongly right-skewed (a few
    last-minute or premium-cabin fares can be many multiples of the typical
    fare), and the median is not pulled toward those extremes the way a
    mean is. ``mean`` and ``trimmed_mean`` are offered for comparison /
    sensitivity analysis.
    """
    fares = fares.dropna()
    if fares.empty:
        return None
    if config.representative_method == "median":
        return float(fares.median())
    if config.representative_method == "mean":
        return float(fares.mean())
    if config.representative_method == "trimmed_mean":
        if len(fares) < 3:
            return float(fares.median())
        return float(_stats.trim_mean(fares.to_numpy(), config.trimmed_mean_proportion))
    raise ValueError(f"Unknown representative_method: {config.representative_method}")


def compute_route_period_fares(df: pd.DataFrame, config: IndexConfig) -> pd.DataFrame:
    """Return one row per (route, period): representative fare + sample size.

    Groups with fewer than ``config.min_observations_per_route_period``
    surviving observations still get a row, but with
    ``sufficient_data=False`` so callers can flag them instead of silently
    trusting a thin sample.
    """
    rows = []
    for (route, period), group in df.groupby(["route", "period"]):
        n = len(group)
        fare = representative_fare(group["standardized_fare"], config)
        rows.append(
            {
                "route": route,
                "period": period,
                "origin": group["origin"].iloc[0].upper(),
                "destination": group["destination"].iloc[0].upper(),
                "representative_fare": fare,
                "observations_used": n,
                "sufficient_data": n >= config.min_observations_per_route_period,
            }
        )
    return pd.DataFrame(rows)


def national_index(route_results: List[RouteIndexResult], method: str) -> Optional[float]:
    """Combine route-level indices into one national index.

    ``arithmetic``: weighted arithmetic mean of route indices
    (sum(weight_i * index_i)). This is the default, and mirrors how
    headline CPI aggregates elementary indices with fixed base-period
    expenditure weights (a Laspeyres-style aggregation).

    ``geometric``: weighted geometric mean of the price relatives
    (exp(sum(weight_i * ln(index_i / 100))) * 100). It dampens the effect
    of any single route spiking, at the cost of being harder to explain to
    a non-technical audience and of implicitly assuming routes substitute
    for each other (a traveller "switches" from an expensive route to a
    cheap one) which is often unrealistic for point-to-point air travel.
    """
    usable = [r for r in route_results if r.route_index is not None and r.weight_normalized]
    if not usable:
        return None

    total_weight = sum(r.weight_normalized for r in usable)
    if total_weight == 0:
        return None

    if method == "arithmetic":
        return sum(r.weight_normalized * r.route_index for r in usable) / total_weight

    if method == "geometric":
        log_sum = sum(r.weight_normalized * np.log(r.route_index / 100.0) for r in usable)
        return float(np.exp(log_sum / total_weight) * 100.0)

    raise ValueError(f"Unknown aggregation_method: {method}")
