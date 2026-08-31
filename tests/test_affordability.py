import pandas as pd

from index_engine.affordability import STATUS_DATA_UNAVAILABLE, STATUS_OK, calculate_affordability


def _income_series(value, period="2026-08", indicator="income_index", source="SYNTHETIC_DEMONSTRATION_DATA"):
    return pd.DataFrame([{"period": period, "indicator": indicator, "value": value, "source": source}])


def test_airfare_rising_faster_than_income_worsens_affordability():
    result = calculate_affordability(110.0, "2026-08", _income_series(105.0))
    assert result.status == STATUS_OK
    assert result.relative_affordability_index > 100


def test_income_rising_faster_than_airfare_improves_affordability():
    result = calculate_affordability(105.0, "2026-08", _income_series(110.0))
    assert result.relative_affordability_index < 100


def test_equal_growth_leaves_affordability_unchanged():
    result = calculate_affordability(105.0, "2026-08", _income_series(105.0))
    assert abs(result.relative_affordability_index - 100.0) < 1e-9


def test_missing_income_series_returns_data_unavailable_not_a_guess():
    result = calculate_affordability(110.0, "2026-08", None)
    assert result.status == STATUS_DATA_UNAVAILABLE
    assert result.relative_affordability_index is None


def test_missing_period_in_income_series_returns_data_unavailable():
    result = calculate_affordability(110.0, "2026-09", _income_series(105.0, period="2026-08"))
    assert result.status == STATUS_DATA_UNAVAILABLE


def test_zero_income_index_returns_data_unavailable_not_a_division_error():
    result = calculate_affordability(110.0, "2026-08", _income_series(0.0))
    assert result.status == STATUS_DATA_UNAVAILABLE
