"""Airfare Price Index / Statistical Modeling Engine.

Public API:

    from index_engine import AirfarePriceIndex, IndexConfig

    engine = AirfarePriceIndex(base_period="2026-01")
    result = engine.calculate(observations=fares_df, current_period="2026-08")
    result.national_index, result.mom_change_pct, result.yoy_change_pct

See docs/methodology.md for the statistical methodology and README.md for
how this module fits into the rest of the SIH pipeline.
"""

from .affordability import AffordabilityResult, calculate_affordability
from .analytics import AirfareAnalytics, AnalyticsResult
from .config import BOOKING_HORIZON_BUCKETS, IndexConfig
from .exceptions import ConfigurationError, IndexEngineError, InsufficientDataError, SchemaError
from .index import AirfarePriceIndex
from .models import CleaningReport, IndexResult, RouteContribution, RouteIndexResult
from .route_analysis import RouteInflationRow
from .route_selection import (
    assign_tiers,
    bidirectional_summary,
    city_level_traffic,
    coverage_at_n,
    coverage_scenarios,
    find_routes_for_target_coverage,
    mark_currently_covered,
    rank_routes_by_traffic,
    target_coverage_table,
    underrepresented_cities,
)
from .traffic import build_dgca_weights
from .volatility import VolatilityConfig, VolatilityResult, calculate_volatility
from .weighting import generate_synthetic_weights

__all__ = [
    "AirfarePriceIndex",
    "IndexConfig",
    "IndexResult",
    "RouteIndexResult",
    "RouteContribution",
    "CleaningReport",
    "BOOKING_HORIZON_BUCKETS",
    "IndexEngineError",
    "ConfigurationError",
    "InsufficientDataError",
    "SchemaError",
    "generate_synthetic_weights",
    "build_dgca_weights",
    "VolatilityConfig",
    "VolatilityResult",
    "calculate_volatility",
    "RouteInflationRow",
    "AffordabilityResult",
    "calculate_affordability",
    "AirfareAnalytics",
    "AnalyticsResult",
    "rank_routes_by_traffic",
    "coverage_at_n",
    "find_routes_for_target_coverage",
    "coverage_scenarios",
    "target_coverage_table",
    "bidirectional_summary",
    "assign_tiers",
    "mark_currently_covered",
    "city_level_traffic",
    "underrepresented_cities",
]

__version__ = "0.1.0"
