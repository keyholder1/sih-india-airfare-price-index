import pandas as pd

from index_engine.volatility import (
    HIGH,
    LOW,
    VolatilityConfig,
    calculate_volatility,
    coefficient_of_variation,
    log_return_stddev,
)


def _obs_df(route_fares: dict, period="2026-08", booking_bucket="15-30"):
    rows = []
    for route, fares in route_fares.items():
        origin, destination = route.split("-")
        for fare in fares:
            rows.append(
                {
                    "route": route,
                    "origin": origin,
                    "destination": destination,
                    "period": period,
                    "standardized_fare": fare,
                    "booking_horizon_bucket": booking_bucket,
                }
            )
    return pd.DataFrame(rows)


def test_constant_prices_have_zero_volatility_and_classify_low():
    cv = coefficient_of_variation(pd.Series([5000, 5000, 5000, 5000]))
    assert cv == 0.0


def test_stable_prices_classify_low():
    df = _obs_df({"BLR-DEL": [4900, 5000, 5100, 5000]})
    result = calculate_volatility(df, "2026-08")
    assert result.route_volatility[0].classification == LOW


def test_highly_dispersed_prices_classify_high():
    df = _obs_df({"BLR-DEL": [3000, 8000, 4000, 9000]})
    result = calculate_volatility(df, "2026-08")
    assert result.route_volatility[0].classification == HIGH


def test_coefficient_of_variation_is_scale_invariant():
    low_level = coefficient_of_variation(pd.Series([4900, 5000, 5100, 5000]))
    high_level = coefficient_of_variation(pd.Series([x * 10 for x in [4900, 5000, 5100, 5000]]))
    assert abs(low_level - high_level) < 1e-9


def test_insufficient_observations_returns_none_not_a_number():
    df = _obs_df({"BLR-DEL": [5000, 5100]})  # below default min_observations of 3
    result = calculate_volatility(df, "2026-08")
    assert result.route_volatility[0].volatility is None
    assert result.route_volatility[0].classification == "INSUFFICIENT_DATA"


def test_single_observation_route_is_insufficient():
    df = _obs_df({"BLR-DEL": [5000]})
    result = calculate_volatility(df, "2026-08")
    assert result.route_volatility[0].classification == "INSUFFICIENT_DATA"


def test_national_volatility_is_weighted_by_provided_weights():
    df = _obs_df({"BLR-DEL": [3000, 8000, 4000, 9000], "DEL-BOM": [4900, 5000, 5100, 5000]})
    weights = pd.DataFrame({"route": ["BLR-DEL", "DEL-BOM"], "weight_normalized": [0.9, 0.1]})
    result = calculate_volatility(df, "2026-08", weights_df=weights)
    # Dominated by the volatile route since it carries 90% of the weight.
    assert result.national_classification == HIGH


def test_booking_horizon_volatility_breaks_down_by_bucket():
    rows = []
    for fare in [4000, 4200, 3900, 4100]:
        rows.append({"route": "BLR-DEL", "origin": "BLR", "destination": "DEL", "period": "2026-08", "standardized_fare": fare, "booking_horizon_bucket": "61+"})
    for fare in [3000, 9000, 4000, 8500]:
        rows.append({"route": "BLR-DEL", "origin": "BLR", "destination": "DEL", "period": "2026-08", "standardized_fare": fare, "booking_horizon_bucket": "0-3"})
    df = pd.DataFrame(rows)
    result = calculate_volatility(df, "2026-08")
    by_bucket = {b.bucket: b.classification for b in result.booking_horizon_volatility}
    assert by_bucket["61+"] == LOW
    assert by_bucket["0-3"] == HIGH


def test_log_return_stddev_needs_at_least_two_periods():
    assert log_return_stddev(pd.Series([5000])) is None
    series = pd.Series([5000, 5250, 5000, 5500], index=["2026-01", "2026-02", "2026-03", "2026-04"])
    result = log_return_stddev(series)
    assert result is not None and result > 0
