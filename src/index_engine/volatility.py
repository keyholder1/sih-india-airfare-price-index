"""Airfare volatility: how UNSTABLE prices are, distinct from how much they MOVED.

The price index (index_engine.index) answers "did airfare get more
expensive." This module answers a different question: "how unpredictable
is the price right now" — a route where every fare clusters near ₹5,000 is
a very different market than one where fares range ₹3,000–₹9,000, even if
both have the same average.

Two methodologies are implemented; the module defaults to one and explains
why rather than returning both as unexplained numbers:

- **Coefficient of variation** (default): std-dev / mean of the fares
  observed for a route in a single period. Chosen as the default because
  it only needs *one* period's cross-sectional observations — appropriate
  for a project that may only have a few months of live scraped data at
  demo time — and it directly matches the intuitive definition of
  volatility ("today's prices for this route are all over the place").
- **Log-return standard deviation**: the standard deviation of
  month-over-month log changes in a route's representative fare, the
  standard definition of volatility in financial time series. Needs
  several months of history to mean anything, which is why it isn't the
  default yet. **It is not wired into ``calculate_volatility``/
  ``compute_route_volatility``** — those two only ever see one period's
  cross-sectional fares (by design, so the coefficient-of-variation path
  needs no history), which is not what this method needs. Setting
  ``VolatilityConfig(method="log_return_stddev")`` and calling
  ``calculate_volatility`` raises ``NotImplementedError`` rather than
  silently returning ``None`` everywhere. To actually use this method once
  enough monthly history exists, call :func:`log_return_stddev` directly
  with your own chronologically-sorted, one-representative-fare-per-period
  ``pandas.Series`` for the route you care about (e.g. built from
  ``aggregation.compute_route_period_fares`` across several periods).

Kept independent of index_engine.index: this module only reads the same
cleaned observations index.py already produces, it does not change or
depend on the price-index calculation itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal, Optional

import numpy as np
import pandas as pd

VolatilityMethod = Literal["coefficient_of_variation", "log_return_stddev"]

LOW = "LOW"
MODERATE = "MODERATE"
HIGH = "HIGH"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class VolatilityConfig:
    """Prototype thresholds — NOT official statistical thresholds. Chosen as
    round, defensible numbers for a coefficient of variation (a CV of 0.25
    means the typical fare swings roughly a quarter of its own value), not
    derived from a large historical calibration."""

    method: VolatilityMethod = "coefficient_of_variation"
    low_threshold: float = 0.10
    high_threshold: float = 0.25
    min_observations: int = 3


def coefficient_of_variation(fares: pd.Series) -> Optional[float]:
    fares = fares.dropna()
    if len(fares) < 2:
        return None
    mean = fares.mean()
    if mean == 0:
        return None
    return float(fares.std(ddof=1) / mean)


def log_return_stddev(representative_fare_series: pd.Series) -> Optional[float]:
    """``representative_fare_series`` must be sorted chronologically (e.g.
    indexed by period) with one representative fare per period."""
    series = representative_fare_series.dropna()
    if len(series) < 2:
        return None
    log_returns = np.log(series / series.shift(1)).dropna()
    if log_returns.empty:
        return None
    if len(log_returns) == 1:
        return float(abs(log_returns.iloc[0]))
    return float(log_returns.std(ddof=1))


def classify(volatility: Optional[float], config: VolatilityConfig) -> str:
    if volatility is None:
        return INSUFFICIENT_DATA
    if volatility < config.low_threshold:
        return LOW
    if volatility > config.high_threshold:
        return HIGH
    return MODERATE


@dataclass
class RouteVolatilityResult:
    route: str
    period: str
    volatility: Optional[float]
    classification: str
    observations_used: int
    method: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BookingHorizonVolatility:
    bucket: str
    volatility: Optional[float]
    classification: str
    observations_used: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VolatilityResult:
    period: str
    method: str
    national_volatility: Optional[float]
    national_classification: str
    route_volatility: List[RouteVolatilityResult]
    high_volatility_routes: List[str]
    low_volatility_routes: List[str]
    observations_used: int
    booking_horizon_volatility: List[BookingHorizonVolatility] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "method": self.method,
            "national_volatility": self.national_volatility,
            "national_classification": self.national_classification,
            "route_volatility": [r.to_dict() for r in self.route_volatility],
            "high_volatility_routes": self.high_volatility_routes,
            "low_volatility_routes": self.low_volatility_routes,
            "observations_used": self.observations_used,
            "booking_horizon_volatility": [b.to_dict() for b in self.booking_horizon_volatility],
        }


def compute_route_volatility(clean_df: pd.DataFrame, period: str, config: VolatilityConfig) -> List[RouteVolatilityResult]:
    """``clean_df`` must have route/period/standardized_fare columns, i.e.
    the same post-cleaning observations index_engine.index works from.

    Raises
    ------
    NotImplementedError
        If ``config.method == "log_return_stddev"``. This function only
        ever has one period's cross-sectional fares (``period_df`` below),
        never the multi-period representative-fare series that method
        needs — see the module docstring and :func:`log_return_stddev`.
    """
    if config.method == "log_return_stddev":
        raise NotImplementedError(
            "VolatilityConfig(method='log_return_stddev') is not usable through "
            "compute_route_volatility()/calculate_volatility() -- they only ever see one period's "
            "cross-sectional fares. Call index_engine.volatility.log_return_stddev(series) directly "
            "with your own multi-period representative-fare series instead. See the module docstring."
        )
    period_df = clean_df[clean_df["period"] == period]
    results = []
    for route, group in period_df.groupby("route"):
        fares = group["standardized_fare"]
        n = len(fares)
        if n < config.min_observations:
            results.append(RouteVolatilityResult(route, period, None, INSUFFICIENT_DATA, n, config.method))
            continue
        vol = coefficient_of_variation(fares)
        results.append(RouteVolatilityResult(route, period, vol, classify(vol, config), n, config.method))
    return results


def _weighted_or_simple_mean(route_results: List[RouteVolatilityResult], weights_df: Optional[pd.DataFrame]) -> Optional[float]:
    usable = [r for r in route_results if r.volatility is not None]
    if not usable:
        return None
    if weights_df is None or not len(weights_df):
        return float(np.mean([r.volatility for r in usable]))

    weight_col = "weight_normalized" if "weight_normalized" in weights_df.columns else "weight"
    weight_map: Dict[str, float] = dict(zip(weights_df["route"], weights_df[weight_col]))
    weighted_pairs = [(r.volatility, weight_map.get(r.route, 0.0)) for r in usable]
    total_weight = sum(w for _, w in weighted_pairs)
    if total_weight == 0:
        return float(np.mean([r.volatility for r in usable]))
    return sum(v * w for v, w in weighted_pairs) / total_weight


def compute_booking_horizon_volatility(clean_df: pd.DataFrame, period: str, config: VolatilityConfig) -> List[BookingHorizonVolatility]:
    if "booking_horizon_bucket" not in clean_df.columns:
        return []
    period_df = clean_df[clean_df["period"] == period]
    results = []
    for bucket, group in period_df.groupby("booking_horizon_bucket"):
        fares = group["standardized_fare"]
        n = len(fares)
        if n < config.min_observations:
            results.append(BookingHorizonVolatility(bucket, None, INSUFFICIENT_DATA, n))
            continue
        vol = coefficient_of_variation(fares)
        results.append(BookingHorizonVolatility(bucket, vol, classify(vol, config), n))
    return sorted(results, key=lambda b: b.bucket)


def calculate_volatility(
    clean_df: pd.DataFrame,
    period: str,
    config: Optional[VolatilityConfig] = None,
    weights_df: Optional[pd.DataFrame] = None,
    include_booking_horizon: bool = True,
) -> VolatilityResult:
    config = config or VolatilityConfig()
    route_results = compute_route_volatility(clean_df, period, config)
    national = _weighted_or_simple_mean(route_results, weights_df)
    national_classification = classify(national, config)

    usable = [r for r in route_results if r.volatility is not None]
    high = sorted(r.route for r in usable if r.classification == HIGH)
    low = sorted(r.route for r in usable if r.classification == LOW)
    observations_used = int(sum(r.observations_used for r in route_results))

    booking_horizon = compute_booking_horizon_volatility(clean_df, period, config) if include_booking_horizon else []

    return VolatilityResult(
        period=period,
        method=config.method,
        national_volatility=national,
        national_classification=national_classification,
        route_volatility=route_results,
        high_volatility_routes=high,
        low_volatility_routes=low,
        observations_used=observations_used,
        booking_horizon_volatility=booking_horizon,
    )
