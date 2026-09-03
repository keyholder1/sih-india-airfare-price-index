import pandas as pd

from index_engine.aggregation import national_index, representative_fare
from index_engine.config import IndexConfig
from index_engine.models import RouteIndexResult


def _route_result(route, index, weight):
    return RouteIndexResult(
        route=route,
        origin=route.split("-")[0],
        destination=route.split("-")[1],
        period="2026-08",
        base_period_fare=5000.0,
        period_fare=5000.0 * index / 100,
        route_index=index,
        observations_used=10,
        weight_raw=weight,
        weight_normalized=weight,
        status="OK",
    )


def test_median_is_robust_to_a_single_extreme_value():
    config = IndexConfig(base_period="2026-01", representative_method="median")
    fares = pd.Series([5000, 5100, 4900, 5050, 500000])
    assert representative_fare(fares, config) == 5050


def test_mean_is_pulled_by_extreme_value():
    config = IndexConfig(base_period="2026-01", representative_method="mean")
    fares = pd.Series([5000, 5100, 4900, 5050, 500000])
    assert representative_fare(fares, config) > 100000


def test_trimmed_mean_between_median_and_mean():
    config = IndexConfig(base_period="2026-01", representative_method="trimmed_mean", trimmed_mean_proportion=0.2)
    fares = pd.Series([5000, 5100, 4900, 5050, 500000])
    median = representative_fare(pd.Series(fares), IndexConfig(base_period="2026-01", representative_method="median"))
    trimmed = representative_fare(fares, config)
    assert trimmed >= median  # trimming with n=5 keeps at least the top-of-normal-range value


def test_arithmetic_weighted_national_index_matches_manual_calculation():
    results = [_route_result("BLR-DEL", 110.0, 0.6), _route_result("DEL-BOM", 105.0, 0.4)]
    result = national_index(results, "arithmetic")
    assert abs(result - 108.0) < 1e-9  # 110*0.6 + 105*0.4 = 108


def test_geometric_national_index_differs_from_arithmetic():
    results = [_route_result("BLR-DEL", 120.0, 0.5), _route_result("DEL-BOM", 100.0, 0.5)]
    arithmetic = national_index(results, "arithmetic")
    geometric = national_index(results, "geometric")
    assert arithmetic == 110.0
    assert geometric < arithmetic  # geometric mean <= arithmetic mean (AM-GM inequality)
