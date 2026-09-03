import math

import pandas as pd
import pytest

from conftest import make_observation, to_df
from forecasting import (
    ForecastingDataset,
    build_forecasting_dataset,
    evaluate_national_baselines,
    forecast_national_index,
    historical_mean_forecast,
    moving_average_forecast,
    naive_forecast,
    national_index_series,
    rolling_origin_backtest,
)
from forecasting.data_access import NATIONAL_COLUMNS, ROUTE_COLUMNS
from forecasting.results import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MODEL_NOT_APPLICABLE,
    STATUS_OK,
    STATUS_TARGET_UNAVAILABLE,
)


def _empty_dataset(national_rows=None) -> ForecastingDataset:
    national_df = pd.DataFrame(national_rows or [], columns=NATIONAL_COLUMNS)
    routes_df = pd.DataFrame([], columns=ROUTE_COLUMNS)
    periods = [r["period"] for r in (national_rows or [])]
    return ForecastingDataset(base_period="2026-01", periods=periods, national=national_df, routes=routes_df)


def _national_row(period, national_index, coverage_rate=1.0):
    row = {c: None for c in NATIONAL_COLUMNS}
    row["period"] = period
    row["national_index"] = national_index
    row["coverage_rate"] = coverage_rate
    return row


def _months(*values, start="2026-01"):
    """Build a calendar-complete pd.Series of monthly values (or None for
    a gap) starting at `start`, labeled with real YYYY-MM periods."""
    periods = pd.period_range(start, periods=len(values), freq="M")
    labels = [p.strftime("%Y-%m") for p in periods]
    return pd.Series([float(v) if v is not None else float("nan") for v in values], index=pd.Index(labels, name="period"))


# --- baseline model functions (gap-aware) --------------------------------------


def test_naive_forecast_returns_most_recent_value():
    series = _months(100.0, 101.0, 103.5)
    assert naive_forecast(series) == 103.5


def test_naive_forecast_none_for_empty_series():
    assert naive_forecast(pd.Series(dtype=float)) is None


def test_naive_forecast_skips_a_trailing_gap_to_find_the_last_real_value():
    series = _months(100.0, 101.0, None)  # Mar is a gap
    assert naive_forecast(series) == 101.0  # Feb, not a fabricated Mar value


def test_naive_forecast_none_when_every_point_is_a_gap():
    series = _months(None, None, None)
    assert naive_forecast(series) is None


def test_historical_mean_forecast_returns_mean_of_all_points():
    series = _months(100.0, 110.0, 120.0)
    assert historical_mean_forecast(series) == pytest.approx(110.0)


def test_historical_mean_forecast_excludes_gap_months_from_the_average():
    series = _months(100.0, None, 120.0)  # mean of [100, 120], NOT (100+0+120)/3
    assert historical_mean_forecast(series) == pytest.approx(110.0)


def test_historical_mean_forecast_of_one_point_is_that_point():
    assert historical_mean_forecast(pd.Series([42.0])) == 42.0


def test_moving_average_returns_none_when_fewer_points_than_window():
    series = _months(100.0, 101.0)
    assert moving_average_forecast(series, window=3) is None


def test_moving_average_uses_only_the_last_window_points():
    series = _months(100.0, 200.0, 10.0, 20.0, 30.0)  # window=3 -> mean(10,20,30)
    assert moving_average_forecast(series, window=3) == pytest.approx(20.0)


def test_moving_average_returns_none_if_any_point_in_the_window_is_a_gap():
    """Unlike naive/historical_mean, moving_average must NOT reach past a
    gap to find enough real points — the literal last `window` calendar
    slots must all be real."""
    series = _months(100.0, None, 30.0, 40.0)  # last 3 slots: [None, 30, 40]
    assert moving_average_forecast(series, window=3) is None


def test_moving_average_rejects_invalid_window():
    with pytest.raises(ValueError):
        moving_average_forecast(pd.Series([1.0, 2.0]), window=0)


# --- rolling_origin_backtest: no-leakage guarantee (with and without gaps) ----


def test_backtest_never_shows_the_model_future_values():
    """Spy on every call: the training window handed to the model must
    never contain the value being predicted, or anything after it."""
    series = _months(10.0, 20.0, 30.0, 40.0, 50.0)
    seen_windows = []

    def spy_model(history):
        seen_windows.append(list(history.values))
        return float(history.dropna().iloc[-1])

    rolling_origin_backtest(series, spy_model, "spy", min_train_size=1, is_synthetic_data=True)

    full_values = list(series.values)
    for i, window in enumerate(seen_windows):
        k = i + 1  # min_train_size=1 -> first window has 1 point
        assert window == full_values[:k]
        assert len(window) <= k


def test_backtest_never_shows_future_values_even_with_a_gap_in_history():
    """Not every fold calls the model (a NaN-target fold is skipped before
    the model ever sees anything), so this checks each window the model
    WAS shown is always some calendar-ordered PREFIX of the full series —
    never containing a value from beyond its own training cutoff."""
    series = _months(10.0, None, 30.0, 40.0, 50.0)
    seen_windows = []

    def spy_model(history):
        seen_windows.append(list(history.values))
        real = history.dropna()
        return float(real.iloc[-1]) if len(real) else None

    rolling_origin_backtest(series, spy_model, "spy", min_train_size=1, is_synthetic_data=True)
    full_values = list(series.values)
    assert len(seen_windows) > 0
    for window in seen_windows:
        expected_prefix = full_values[: len(window)]
        for a, b in zip(window, expected_prefix):
            assert (math.isnan(a) and math.isnan(b)) or a == b


def test_backtest_walk_forward_pattern_matches_expected_train_sizes():
    series = _months(1.0, 2.0, 3.0, 4.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    train_sizes = [f.data_points_used for f in result.forecasts]
    assert train_sizes == [1, 2, 3]  # predicting month 2, 3, 4
    predicted_periods = [f.forecast_period for f in result.forecasts]
    assert predicted_periods == list(series.index[1:])


# --- calendar-gap regression tests (Stage 3.1 core fix) ------------------------


def test_one_missing_middle_month_does_not_corrupt_fold_labeling():
    """Jan, Feb, Mar(gap), Apr. The Mar fold must be skipped (target
    unavailable) rather than silently scored; the Apr fold must still be
    correctly labeled horizon=1 relative to Mar's calendar position, not
    silently compared against Feb as if Mar never existed."""
    series = _months(100.0, 105.0, None, 110.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)

    by_period = {f.forecast_period: f for f in result.forecasts}
    assert by_period["2026-03"].status == STATUS_TARGET_UNAVAILABLE
    assert by_period["2026-03"].forecast_value is None
    assert by_period["2026-04"].status == STATUS_OK
    assert by_period["2026-04"].forecast_value == 105.0
    assert by_period["2026-04"].horizon == 1
    assert result.number_of_forecasts == 2
    assert "target period had no trustworthy" in result.notes


def test_multiple_consecutive_missing_months_are_all_skipped_individually():
    series = _months(100.0, None, None, None, 120.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    statuses_by_period = {f.forecast_period: f.status for f in result.forecasts}
    assert statuses_by_period["2026-02"] == STATUS_TARGET_UNAVAILABLE
    assert statuses_by_period["2026-03"] == STATUS_TARGET_UNAVAILABLE
    assert statuses_by_period["2026-04"] == STATUS_TARGET_UNAVAILABLE
    assert statuses_by_period["2026-05"] == STATUS_OK
    may_fold = next(f for f in result.forecasts if f.forecast_period == "2026-05")
    assert may_fold.forecast_value == 100.0
    assert may_fold.horizon == 1


def test_missing_target_month_is_skipped_not_scored_as_an_error():
    series = _months(100.0, 105.0, None)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    target_fold = next(f for f in result.forecasts if f.forecast_period == "2026-03")
    assert target_fold.status == STATUS_TARGET_UNAVAILABLE
    assert target_fold.forecast_value is None
    assert result.number_of_forecasts == 1


def test_moving_average_behavior_across_gaps_in_backtest():
    """window=2: a fold whose 2 most recent calendar slots straddle a gap
    must be skipped (MODEL_NOT_APPLICABLE), not silently computed from
    non-adjacent months."""
    series = _months(10.0, None, 30.0, 40.0)
    result = rolling_origin_backtest(series, moving_average_forecast, "moving_average", min_train_size=2, window=2, is_synthetic_data=True)
    by_period = {f.forecast_period: f for f in result.forecasts}
    assert by_period["2026-03"].status == STATUS_MODEL_NOT_APPLICABLE
    assert by_period["2026-04"].status == STATUS_MODEL_NOT_APPLICABLE
    assert result.number_of_forecasts == 0
    assert result.status == STATUS_INSUFFICIENT_DATA


def test_correct_horizon_labeling_regardless_of_gap_position():
    """Every scored fold must report horizon=1 and its forecast_period
    must be exactly one calendar month after the fold's training cutoff
    position — verified directly via shift_period, not just trusted."""
    from index_engine.utils import shift_period

    series = _months(100.0, None, 110.0, 115.0, None, 120.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    for f in result.forecasts:
        assert f.horizon == 1
        train_last_period = f.training_period[-1]
        assert shift_period(train_last_period, 1) == f.forecast_period


def test_contiguous_data_preserves_prior_stage3_results():
    """Regression lock: a fully gap-free series must produce IDENTICAL
    numbers to what Stage 3 (pre-3.1) produced, proving the fix changes
    nothing for the well-behaved case."""
    series = _months(1.0, 2.0, 4.0, 8.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    expected_mae = (1 + 2 + 4) / 3
    expected_rmse = math.sqrt((1**2 + 2**2 + 4**2) / 3)
    assert result.mae == pytest.approx(expected_mae)
    assert result.rmse == pytest.approx(expected_rmse)
    assert result.number_of_forecasts == 3


def test_rolling_origin_backtest_raises_on_non_calendar_complete_series():
    """Defensive guard: a series with a row actually removed (not NaN'd)
    for a gap month must be rejected outright, not silently mislabeled."""
    series = pd.Series([100.0, 110.0], index=["2026-01", "2026-03"])
    with pytest.raises(ValueError, match="Calendar-contiguity violated"):
        rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)


# --- error metric correctness (hand-computed, gap-free case unchanged) --------


def test_mae_and_rmse_match_manual_calculation():
    series = _months(1.0, 2.0, 4.0, 8.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    expected_mae = (1 + 2 + 4) / 3
    expected_rmse = math.sqrt((1**2 + 2**2 + 4**2) / 3)
    assert result.mae == pytest.approx(expected_mae)
    assert result.rmse == pytest.approx(expected_rmse)
    assert result.number_of_forecasts == 3


def test_mase_matches_manual_calculation():
    series = _months(1.0, 2.0, 4.0, 8.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    expected_mase = (2.0 + (4 / 1.5)) / 2
    assert result.mase == pytest.approx(expected_mase)
    assert "excluded" in result.mase_status


def test_mase_is_none_when_every_fold_has_a_single_point_training_window():
    series = _months(1.0, 2.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    assert result.number_of_forecasts == 1
    assert result.mase is None
    assert "could not be computed" in result.mase_status


# --- insufficient data / skipped folds -----------------------------------------


def test_backtest_reports_insufficient_data_status_when_zero_folds_possible():
    series = _months(100.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    assert result.number_of_forecasts == 0
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.mae is None and result.rmse is None and result.mase is None


def test_moving_average_backtest_skips_early_folds_not_errors():
    series = _months(10.0, 20.0, 30.0, 40.0, 50.0)
    result = rolling_origin_backtest(series, moving_average_forecast, "moving_average", min_train_size=1, window=3, is_synthetic_data=True)
    statuses = [f.status for f in result.forecasts]
    assert statuses.count(STATUS_MODEL_NOT_APPLICABLE) == 2
    assert statuses.count(STATUS_OK) == 2
    assert result.number_of_forecasts == 2
    assert "skipped" in result.notes


def test_low_fold_count_is_flagged_in_notes():
    series = _months(1.0, 2.0, 3.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    assert result.number_of_forecasts == 2
    assert "illustrative" in result.notes


# --- national_index_series: calendar-complete, gap-preserving, coverage-aware -


def test_national_index_series_preserves_every_calendar_period_as_nan_not_dropped():
    dataset = _empty_dataset(
        [
            _national_row("2026-01", 100.0),
            _national_row("2026-02", None),
            _national_row("2026-03", 102.0),
        ]
    )
    series = national_index_series(dataset)
    assert list(series.index) == ["2026-01", "2026-02", "2026-03"]
    assert series.loc["2026-01"] == 100.0
    assert math.isnan(series.loc["2026-02"])
    assert series.loc["2026-03"] == 102.0


def test_national_index_series_min_coverage_rate_none_applies_no_filtering():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0, coverage_rate=0.1), _national_row("2026-02", 105.0, coverage_rate=1.0)]
    )
    series = national_index_series(dataset, min_coverage_rate=None)
    assert series.loc["2026-01"] == 100.0
    assert series.loc["2026-02"] == 105.0


def test_national_index_series_min_coverage_rate_filters_low_quality_periods():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0, coverage_rate=0.1), _national_row("2026-02", 105.0, coverage_rate=1.0)]
    )
    series = national_index_series(dataset, min_coverage_rate=0.5)
    assert math.isnan(series.loc["2026-01"])
    assert series.loc["2026-02"] == 105.0


# --- forecast_national_index ---------------------------------------------------


def test_forecast_national_index_naive_matches_last_value():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 105.0), _national_row("2026-03", 110.0)]
    )
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert result.forecast_value == 110.0
    assert result.forecast_period == "2026-04"
    assert result.status == STATUS_OK
    assert result.is_synthetic_data is True
    assert result.model_used == "naive"
    assert result.data_points_used == 3


def test_forecast_national_index_anchors_to_last_real_period_when_latest_is_a_gap():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 105.0), _national_row("2026-03", None)]
    )
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert result.forecast_period == "2026-03"
    assert result.forecast_value == 105.0


def test_forecast_national_index_rejects_horizon_other_than_one():
    dataset = _empty_dataset([_national_row("2026-01", 100.0)])
    with pytest.raises(ValueError):
        forecast_national_index(dataset, is_synthetic_data=True, model="naive", horizon=2)


def test_forecast_national_index_rejects_unknown_model():
    dataset = _empty_dataset([_national_row("2026-01", 100.0)])
    with pytest.raises(ValueError):
        forecast_national_index(dataset, is_synthetic_data=True, model="not_a_real_model")


def test_forecast_national_index_insufficient_data_when_all_values_missing():
    dataset = _empty_dataset([_national_row("2026-01", None)])
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert result.forecast_value is None
    assert result.status == STATUS_INSUFFICIENT_DATA


def test_forecast_national_index_model_not_applicable_for_moving_average_with_too_little_history():
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 105.0)])
    result = forecast_national_index(dataset, is_synthetic_data=True, model="moving_average", window=5)
    assert result.forecast_value is None
    assert result.status == STATUS_MODEL_NOT_APPLICABLE


def test_forecast_national_index_no_interval_when_too_few_backtest_folds():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 105.0), _national_row("2026-03", 108.0)]
    )
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert result.lower_bound is None and result.upper_bound is None
    assert "No confidence interval" in result.notes


def test_forecast_national_index_produces_interval_with_enough_folds():
    values = [100.0, 101.0, 99.0, 103.0, 102.0, 105.0]
    rows = [_national_row(f"2026-0{i+1}", v) for i, v in enumerate(values)]
    dataset = _empty_dataset(rows)
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert result.lower_bound is not None
    assert result.upper_bound is not None
    assert result.lower_bound < result.forecast_value < result.upper_bound


def test_forecast_national_index_respects_min_coverage_rate():
    dataset = _empty_dataset(
        [
            _national_row("2026-01", 100.0, coverage_rate=1.0),
            _national_row("2026-02", 999.0, coverage_rate=0.05),
        ]
    )
    filtered = forecast_national_index(dataset, is_synthetic_data=True, model="naive", min_coverage_rate=0.5)
    unfiltered = forecast_national_index(dataset, is_synthetic_data=True, model="naive", min_coverage_rate=None)
    assert filtered.forecast_value == 100.0
    assert unfiltered.forecast_value == 999.0


# --- evaluate_national_baselines ------------------------------------------------


def test_evaluate_national_baselines_returns_all_default_models():
    values = [100.0, 101.0, 99.0, 103.0, 102.0]
    rows = [_national_row(f"2026-0{i+1}", v) for i, v in enumerate(values)]
    dataset = _empty_dataset(rows)
    results = evaluate_national_baselines(dataset, is_synthetic_data=True)
    assert set(results.keys()) == {"naive", "historical_mean", "moving_average"}
    for evaluation in results.values():
        assert evaluation.status in (STATUS_OK, STATUS_INSUFFICIENT_DATA)


def test_evaluate_national_baselines_respects_explicit_model_subset():
    values = [100.0, 101.0, 99.0]
    rows = [_national_row(f"2026-0{i+1}", v) for i, v in enumerate(values)]
    dataset = _empty_dataset(rows)
    results = evaluate_national_baselines(dataset, is_synthetic_data=True, models=["naive"])
    assert set(results.keys()) == {"naive"}


# --- serialization ---------------------------------------------------------------


def test_forecast_result_to_dict_is_json_serializable_shape():
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 105.0)])
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    d = result.to_dict()
    assert d["forecast_value"] == 105.0
    assert d["model_used"] == "naive"
    assert d["is_synthetic_data"] is True
    assert isinstance(d["training_period"], list)


def test_model_evaluation_result_to_dict_includes_nested_forecasts():
    series = _months(1.0, 2.0, 3.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1, is_synthetic_data=True)
    d = result.to_dict()
    assert d["model"] == "naive"
    assert isinstance(d["forecasts"], list)
    assert isinstance(d["forecasts"][0], dict)
    assert "forecast_value" in d["forecasts"][0]


# --- integration: real dataset built from the repo's own sample fares --------


def test_end_to_end_against_real_sample_fares():
    fares = to_df(
        [
            make_observation(
                flight_date=f"2026-0{month}-15",
                booking_date=f"2026-0{month}-05",
                total_fare=5000.0 + month * 100 + i,
            )
            for month in range(1, 6)
            for i in range(5)
        ]
    )
    dataset = build_forecasting_dataset(fares, base_period="2026-01")
    forecast = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert forecast.status == STATUS_OK
    assert forecast.forecast_period == "2026-06"

    evaluations = evaluate_national_baselines(dataset, is_synthetic_data=True)
    assert evaluations["naive"].status == STATUS_OK


# --- Fix 3: is_synthetic_data is a required parameter everywhere -------------


def test_forecast_national_index_requires_is_synthetic_data():
    dataset = _empty_dataset([_national_row("2026-01", 100.0)])
    with pytest.raises(TypeError):
        forecast_national_index(dataset, model="naive")


def test_evaluate_national_baselines_requires_is_synthetic_data():
    dataset = _empty_dataset([_national_row("2026-01", 100.0)])
    with pytest.raises(TypeError):
        evaluate_national_baselines(dataset)


def test_rolling_origin_backtest_requires_is_synthetic_data():
    series = _months(1.0, 2.0, 3.0)
    with pytest.raises(TypeError):
        rolling_origin_backtest(series, naive_forecast, "naive", min_train_size=1)


# --- Fix 4: evaluate_national_baselines validates the models argument --------


def test_evaluate_national_baselines_rejects_unknown_model_name():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 105.0), _national_row("2026-03", 110.0)]
    )
    with pytest.raises(ValueError, match="Unknown model"):
        evaluate_national_baselines(dataset, is_synthetic_data=True, models=["naive", "not_a_real_model"])


def test_evaluate_national_baselines_accepts_valid_model_names():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 105.0), _national_row("2026-03", 110.0)]
    )
    results = evaluate_national_baselines(dataset, is_synthetic_data=True, models=["naive", "historical_mean"])
    assert set(results.keys()) == {"naive", "historical_mean"}


# --- Fix 5: min_train_size is explicitly validated ----------------------------


def test_rolling_origin_backtest_rejects_zero_min_train_size():
    series = _months(1.0, 2.0, 3.0)
    with pytest.raises(ValueError, match="min_train_size must be >= 1"):
        rolling_origin_backtest(series, naive_forecast, "naive", is_synthetic_data=True, min_train_size=0)


def test_rolling_origin_backtest_rejects_negative_min_train_size():
    series = _months(1.0, 2.0, 3.0)
    with pytest.raises(ValueError, match="min_train_size must be >= 1"):
        rolling_origin_backtest(series, naive_forecast, "naive", is_synthetic_data=True, min_train_size=-1)


def test_rolling_origin_backtest_accepts_valid_min_train_size():
    series = _months(1.0, 2.0, 3.0, 4.0)
    result = rolling_origin_backtest(series, naive_forecast, "naive", is_synthetic_data=True, min_train_size=1)
    assert result.status == STATUS_OK


# --- Fix 7A: exactly one valid observation -------------------------------------


def test_dataset_with_exactly_one_valid_observation():
    """A ForecastingDataset built from a single valid fare observation:
    one period, but index_engine's default
    min_observations_per_route_period=3 means national_index is None for
    that period too (correctly — one observation isn't enough for the
    engine to trust a representative fare). Every downstream function
    must degrade honestly (no crash, no fabricated value) rather than
    assume "one point" means "one usable point"."""
    fares = to_df([make_observation(flight_date="2026-01-15", booking_date="2026-01-01", total_fare=5000.0)])
    dataset = build_forecasting_dataset(fares, base_period="2026-01")
    assert dataset.periods == ["2026-01"]
    assert dataset.national.loc[0, "national_index"] is None  # engine correctly refuses, too few observations

    forecast = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert forecast.status == STATUS_INSUFFICIENT_DATA
    assert forecast.forecast_value is None
    assert forecast.data_points_used == 0

    evaluations = evaluate_national_baselines(dataset, is_synthetic_data=True)
    assert evaluations["naive"].status == STATUS_INSUFFICIENT_DATA
    assert evaluations["naive"].number_of_forecasts == 0


# --- Fix 7B: missing final month -----------------------------------------------


def test_missing_final_month_anchors_forecast_to_last_real_period():
    """A calendar-complete series where the LATEST month has no usable
    national_index. forecast_national_index() must anchor to the last
    REAL period (per the Stage 3.1 design), not fabricate a value for,
    or silently skip past, the missing final month."""
    dataset = _empty_dataset(
        [
            _national_row("2026-01", 100.0),
            _national_row("2026-02", 105.0),
            _national_row("2026-03", 110.0),
            _national_row("2026-04", None),  # latest month, missing
        ]
    )
    result = forecast_national_index(dataset, is_synthetic_data=True, model="naive")
    assert result.forecast_period == "2026-04"  # one month after Mar (last real), not May
    assert result.forecast_value == 110.0
    assert result.status == STATUS_OK
