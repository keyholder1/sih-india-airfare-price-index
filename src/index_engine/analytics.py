"""Unified analytics layer: price index + volatility + route inflation +
optional affordability, in one call — while every piece underneath
(:class:`~index_engine.index.AirfarePriceIndex`, :mod:`volatility`,
:mod:`route_analysis`, :mod:`affordability`) stays independently usable.
``AirfarePriceIndex`` itself is untouched and works standalone without
this module ever being imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import pandas as pd

from . import cleaning, normalization, validation
from .affordability import AffordabilityResult, calculate_affordability
from .config import IndexConfig
from .index import AirfarePriceIndex
from .models import IndexResult
from .route_analysis import RouteInflationRow, build_route_inflation_table, inflation_matrix, route_map_objects, top_rankings
from .utils import shift_period
from .volatility import VolatilityConfig, VolatilityResult, calculate_volatility


def _clean_for_volatility(observations: Union[pd.DataFrame, list], config: IndexConfig) -> pd.DataFrame:
    """Re-runs the same validation/normalization/cleaning steps index.py
    uses, since AirfarePriceIndex does not expose its internal cleaned
    DataFrame — volatility needs the individual observations, not just the
    collapsed representative fares the price index returns."""
    df = observations.copy() if isinstance(observations, pd.DataFrame) else pd.DataFrame(list(observations))
    valid, _ = validation.validate_observations(df, fare_field=config.fare_field)
    if len(valid) == 0:
        return valid
    enriched = normalization.enrich(valid, config)
    if config.booking_horizon_filter:
        enriched = enriched[enriched["booking_horizon_bucket"] == config.booking_horizon_filter]
    clean, _ = cleaning.clean_observations(enriched, config, total_input=len(valid))
    return clean


def _empty_volatility_result(period: str, method: str) -> VolatilityResult:
    return VolatilityResult(
        period=period, method=method, national_volatility=None, national_classification="INSUFFICIENT_DATA",
        route_volatility=[], high_volatility_routes=[], low_volatility_routes=[], observations_used=0,
        booking_horizon_volatility=[],
    )


@dataclass
class AnalyticsResult:
    price_index: IndexResult
    volatility: VolatilityResult
    route_inflation: List[RouteInflationRow]
    rankings: Dict[str, List[RouteInflationRow]]
    route_map_objects: List[dict]
    traffic_weight_coverage: Optional[float]
    affordability: Optional[AffordabilityResult]

    def inflation_matrix(self, metric: str = "mom") -> pd.DataFrame:
        return inflation_matrix(self.route_inflation, metric=metric)

    def to_dict(self) -> dict:
        return {
            "price_index": self.price_index.to_dict(),
            "volatility": self.volatility.to_dict(),
            "route_inflation": [r.to_dict() for r in self.route_inflation],
            "rankings": {k: [r.to_dict() for r in v] for k, v in self.rankings.items()},
            "route_map_objects": self.route_map_objects,
            "traffic_weight_coverage": self.traffic_weight_coverage,
            "affordability": self.affordability.to_dict() if self.affordability else None,
        }


class AirfareAnalytics:
    """Unified entry point combining the price index, volatility, and
    route-level inflation/heatmap analysis, with optional affordability.

    ``weights`` should come from either
    :func:`index_engine.weighting.generate_synthetic_weights` or
    :func:`index_engine.traffic.build_dgca_weights` — this class doesn't
    care which, it just passes them through to ``AirfarePriceIndex``.
    """

    def __init__(
        self,
        base_period: str,
        weights: Optional[pd.DataFrame] = None,
        config: Optional[IndexConfig] = None,
        volatility_config: Optional[VolatilityConfig] = None,
        traffic_weight_coverage: Optional[float] = None,
    ) -> None:
        self.base_period = base_period
        self.config = config or IndexConfig(base_period=base_period)
        self.engine = AirfarePriceIndex(base_period=base_period, weights=weights, config=self.config)
        self.volatility_config = volatility_config or VolatilityConfig()
        # Populate from traffic.build_dgca_weights(...)[1]["traffic_weight_coverage"]
        # when using DGCA-derived weights; leave None for synthetic weights,
        # since "coverage of national traffic" is meaningless for those.
        self.traffic_weight_coverage = traffic_weight_coverage
        self._weights = weights

    def calculate(
        self,
        observations: Union[pd.DataFrame, list],
        current_period: str,
        income_series: Optional[pd.DataFrame] = None,
        income_indicator: str = "income_index",
    ) -> AnalyticsResult:
        price_index = self.engine.calculate(observations, current_period)
        prev_month_result = self.engine.calculate(observations, shift_period(current_period, -1))
        prev_year_result = self.engine.calculate(observations, shift_period(current_period, -12))

        clean_df = _clean_for_volatility(observations, self.config)
        if len(clean_df):
            weights_for_volatility = pd.DataFrame(
                [{"route": r.route, "weight_normalized": r.weight_normalized or 0.0} for r in price_index.route_indices]
            )
            volatility = calculate_volatility(clean_df, current_period, self.volatility_config, weights_df=weights_for_volatility)
        else:
            volatility = _empty_volatility_result(current_period, self.volatility_config.method)

        volatility_by_route = {r.route: r.volatility for r in volatility.route_volatility if r.volatility is not None}

        traffic_weight_by_route: Dict[str, float] = {}
        if self._weights is not None and "national_weight" in self._weights.columns:
            weights_copy = self._weights.copy()
            weights_copy["route"] = weights_copy["origin"].str.upper() + "-" + weights_copy["destination"].str.upper()
            traffic_weight_by_route = dict(zip(weights_copy["route"], weights_copy["national_weight"]))

        route_inflation = build_route_inflation_table(
            price_index,
            prev_month_result,
            prev_year_result,
            price_index.route_contributions,
            volatility_by_route=volatility_by_route,
            traffic_weight_by_route=traffic_weight_by_route,
        )
        rankings = top_rankings(route_inflation)
        map_objects = route_map_objects(route_inflation)

        affordability = None
        if income_series is not None:
            affordability = calculate_affordability(price_index.national_index, current_period, income_series, income_indicator)

        return AnalyticsResult(
            price_index=price_index,
            volatility=volatility,
            route_inflation=route_inflation,
            rankings=rankings,
            route_map_objects=map_objects,
            traffic_weight_coverage=self.traffic_weight_coverage,
            affordability=affordability,
        )
