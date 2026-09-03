"""Numeric dtype safety regression tests (Stage 3.1 requirement 6).

Confirms both halves of the fix: (1) the landmine actually exists as
documented — an all-``None`` column really does come back as ``object``
dtype from pandas, not ``float64`` — and (2) ``to_numeric_safe`` reliably
neutralizes it without fabricating any value.
"""

import pandas as pd

from conftest import make_observation, to_df
from forecasting import build_forecasting_dataset, to_numeric_safe


def _route_rows(origin, destination, flight_date, fare, n=5):
    return [
        make_observation(
            origin=origin,
            destination=destination,
            flight_date=flight_date,
            booking_date=pd.Timestamp(flight_date) - pd.Timedelta(days=10),
            total_fare=fare + i,
        )
        for i in range(n)
    ]


def test_yoy_change_pct_and_traffic_weight_are_object_dtype_when_all_none():
    """Confirms the landmine this fix targets actually exists in the real
    dataset shape — if this ever stops being true (e.g. pandas changes
    inference behavior), the test itself should be revisited, not deleted."""
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01"])
    assert dataset.national["yoy_change_pct"].dtype == object
    assert dataset.routes["traffic_weight"].dtype == object


def test_to_numeric_safe_coerces_all_none_columns_to_float_nan():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01"])

    coerced_yoy = to_numeric_safe(dataset.national["yoy_change_pct"])
    assert coerced_yoy.dtype == "float64"
    assert coerced_yoy.isna().all()  # missing stays missing, nothing fabricated

    coerced_traffic = to_numeric_safe(dataset.routes["traffic_weight"])
    assert coerced_traffic.dtype == "float64"
    assert coerced_traffic.isna().all()


def test_to_numeric_safe_preserves_real_numeric_values():
    series = pd.Series([1.5, None, 3.0], dtype=object)
    coerced = to_numeric_safe(series)
    assert coerced.dtype == "float64"
    assert coerced.tolist()[0] == 1.5
    assert coerced.isna().tolist()[1] is True
    assert coerced.tolist()[2] == 3.0


def test_to_numeric_safe_coerces_unparseable_strings_to_nan_not_an_error():
    series = pd.Series(["1.5", "not-a-number", "3.0"])
    coerced = to_numeric_safe(series)
    assert coerced.dtype == "float64"
    assert coerced.isna().tolist() == [False, True, False]
