import sys
from pathlib import Path

import pandas as pd

from index_engine import AirfareAnalytics, IndexConfig
from index_engine.traffic import build_dgca_weights
from index_engine.weighting import generate_synthetic_weights

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))
from generate_sample_fares import generate  # noqa: E402

REAL_DGCA_CSV = Path(__file__).parent.parent / "data" / "traffic" / "dgca_domestic_city_pairs.csv"

ROUTES = [
    ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
    ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
    ("CCU", "DEL"), ("BLR", "BOM"),
]


def test_analytics_runs_end_to_end_with_synthetic_weights():
    fares = generate()
    weights = generate_synthetic_weights(sorted((fares.origin + "-" + fares.destination).unique()))
    analytics = AirfareAnalytics(base_period="2026-01", weights=weights)
    result = analytics.calculate(fares, current_period="2026-08")

    assert result.price_index.national_index is not None
    assert result.volatility.national_volatility is not None
    assert len(result.route_inflation) == result.price_index.routes_total
    assert result.traffic_weight_coverage is None  # synthetic weights carry no traffic coverage
    assert result.affordability is None  # no income series supplied


def test_analytics_runs_end_to_end_with_real_dgca_weights():
    fares = generate()
    engine_weights, diagnostics = build_dgca_weights(str(REAL_DGCA_CSV), ROUTES)
    analytics = AirfareAnalytics(
        base_period="2026-01", weights=engine_weights, traffic_weight_coverage=diagnostics["traffic_weight_coverage"]
    )
    result = analytics.calculate(fares, current_period="2026-08")

    assert result.price_index.national_index is not None
    assert result.traffic_weight_coverage == diagnostics["traffic_weight_coverage"]
    routes_with_traffic_weight = [r for r in result.route_inflation if r.traffic_weight is not None]
    assert len(routes_with_traffic_weight) == len(ROUTES)


def test_analytics_with_affordability_data():
    fares = generate()
    weights = generate_synthetic_weights(sorted((fares.origin + "-" + fares.destination).unique()))
    income_series = pd.DataFrame(
        [{"period": "2026-08", "indicator": "income_index", "value": 103.2, "source": "SYNTHETIC_DEMONSTRATION_DATA"}]
    )
    analytics = AirfareAnalytics(base_period="2026-01", weights=weights)
    result = analytics.calculate(fares, current_period="2026-08", income_series=income_series)
    assert result.affordability is not None
    assert result.affordability.status == "OK"


def test_inflation_matrix_is_accessible_from_analytics_result():
    fares = generate()
    weights = generate_synthetic_weights(sorted((fares.origin + "-" + fares.destination).unique()))
    analytics = AirfareAnalytics(base_period="2026-01", weights=weights)
    result = analytics.calculate(fares, current_period="2026-08")
    matrix = result.inflation_matrix(metric="mom")
    assert "BLR" in matrix.index
    assert "DEL" in matrix.columns
