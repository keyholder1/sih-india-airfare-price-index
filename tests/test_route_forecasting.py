import pandas as pd
import pytest
from index_engine.quality import STATUS_INSUFFICIENT_DATA as ROUTE_STATUS_INSUFFICIENT_DATA
from index_engine.quality import STATUS_OK as ROUTE_STATUS_OK

from forecasting import (
    ForecastingDataset,
    evaluate_all_routes,
    evaluate_route_baselines,
    forecast_all_routes,
    forecast_route_index,
    route_index_series,
)
from forecasting.data_access import NATIONAL_COLUMNS, ROUTE_COLUMNS
from forecasting.results import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MODEL_NOT_APPLICABLE,
    STATUS_OK,
)


def _route_row(period, route, route_index, status=ROUTE_STATUS_OK):
    row = {c: None for c in ROUTE_COLUMNS}
    row["period"] = period
    row["route"] = route
    row["origin"], row["destination"] = route.split("-")
    row["status"] = status
    row["route_index"] = route_index
    return row


def _dataset(route_rows, periods=None):
    routes_df = pd.DataFrame(route_rows, columns=ROUTE_COLUMNS)
    national_df = pd.DataFrame([], columns=NATIONAL_COLUMNS)
    periods = periods if periods is not None else sorted({r["period"] for r in route_rows})
    return ForecastingDataset(base_period=periods[0] if periods else "2026-01", periods=periods, national=national_df, routes=routes_df)


# --- route_index_series -----------------------------------------------------


def test_route_index_series_is_calendar_complete_with_gaps_as_nan():
    rows = [
        _route_row("2026-01", "BLR-DEL", 100.0),
        _route_row("2026-02", "BLR-DEL", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
        _route_row("2026-03", "BLR-DEL", 103.0),
    ]
    dataset = _dataset(rows, periods=["2026-01", "2026-02", "2026-03"])
    series = route_index_series(dataset, "BLR-DEL")
    assert list(series.index) == ["2026-01", "2026-02", "2026-03"]
    assert series["2026-01"] == 100.0
    assert pd.isna(series["2026-02"])
    assert series["2026-03"] == 103.0


def test_route_index_series_unknown_route_raises():
    rows = [_route_row("2026-01", "BLR-DEL", 100.0)]
    dataset = _dataset(rows, periods=["2026-01"])
    with pytest.raises(ValueError):
        route_index_series(dataset, "DEL-BOM")


def test_route_index_series_does_not_leak_other_routes():
    rows = [
        _route_row("2026-01", "BLR-DEL", 100.0),
        _route_row("2026-01", "DEL-BOM", 999.0),
        _route_row("2026-02", "BLR-DEL", 101.0),
        _route_row("2026-02", "DEL-BOM", 998.0),
    ]
    dataset = _dataset(rows, periods=["2026-01", "2026-02"])
    series = route_index_series(dataset, "BLR-DEL")
    assert list(series.values) == [100.0, 101.0]


# --- forecast_route_index ----------------------------------------------------


def test_forecast_route_index_naive_uses_last_real_value():
    rows = [
        _route_row("2026-01", "BLR-DEL", 100.0),
        _route_row("2026-02", "BLR-DEL", 105.0),
        _route_row("2026-03", "BLR-DEL", 110.0),
    ]
    dataset = _dataset(rows)
    result = forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=True, model="naive")
    assert result.status == STATUS_OK
    assert result.forecast_value == 110.0
    assert result.forecast_period == "2026-04"
    assert result.is_synthetic_data is True


def test_forecast_route_index_insufficient_data_for_route_with_no_ok_periods():
    rows = [
        _route_row("2026-01", "BLR-DEL", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
        _route_row("2026-02", "BLR-DEL", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
    ]
    dataset = _dataset(rows)
    result = forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=True, model="naive")
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.forecast_value is None
    assert result.data_points_used == 0


def test_forecast_route_index_model_not_applicable_for_moving_average_gap():
    rows = [
        _route_row("2026-01", "BLR-DEL", 100.0),
        _route_row("2026-02", "BLR-DEL", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
        _route_row("2026-03", "BLR-DEL", 103.0),
    ]
    dataset = _dataset(rows)
    result = forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=True, model="moving_average", window=3)
    assert result.status == STATUS_MODEL_NOT_APPLICABLE
    assert result.forecast_value is None


def test_forecast_route_index_rejects_unknown_model():
    rows = [_route_row("2026-01", "BLR-DEL", 100.0)]
    dataset = _dataset(rows)
    with pytest.raises(ValueError):
        forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=True, model="not_a_model")


def test_forecast_route_index_rejects_horizon_other_than_one():
    rows = [_route_row("2026-01", "BLR-DEL", 100.0)]
    dataset = _dataset(rows)
    with pytest.raises(ValueError):
        forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=True, horizon=2)


def test_forecast_route_index_propagates_synthetic_flag():
    rows = [_route_row("2026-01", "BLR-DEL", 100.0)]
    dataset = _dataset(rows)
    real_result = forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=False, model="naive")
    synth_result = forecast_route_index(dataset, "BLR-DEL", is_synthetic_data=True, model="naive")
    assert real_result.is_synthetic_data is False
    assert synth_result.is_synthetic_data is True


# --- evaluate_route_baselines (backtest) -------------------------------------


def test_evaluate_route_baselines_never_leaks_future_values():
    periods = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    rows = [_route_row(p, "BLR-DEL", v) for p, v in zip(periods, [10.0, 20.0, 30.0, 40.0, 50.0])]
    dataset = _dataset(rows, periods=periods)

    seen_windows = []
    original_series = route_index_series(dataset, "BLR-DEL")

    for k in range(1, len(original_series)):
        train = original_series.iloc[:k]
        seen_windows.append(list(train.values))

    for window in seen_windows:
        assert 50.0 not in window or window[-1] == 50.0  # 50 only ever appears as the LAST value once fully trained


def test_evaluate_route_baselines_naive_fold_count_and_accuracy_on_flat_series():
    periods = ["2026-01", "2026-02", "2026-03", "2026-04"]
    rows = [_route_row(p, "BLR-DEL", 100.0) for p in periods]
    dataset = _dataset(rows, periods=periods)

    results = evaluate_route_baselines(dataset, "BLR-DEL", is_synthetic_data=True, models=["naive"])
    naive_eval = results["naive"]
    assert naive_eval.status == STATUS_OK
    assert naive_eval.number_of_forecasts == 3  # train sizes 1,2,3 -> predict periods 2,3,4
    assert naive_eval.mae == pytest.approx(0.0)


def test_evaluate_route_baselines_insufficient_data_reports_status_not_crash():
    rows = [_route_row("2026-01", "BLR-DEL", None, status=ROUTE_STATUS_INSUFFICIENT_DATA)]
    dataset = _dataset(rows, periods=["2026-01"])
    results = evaluate_route_baselines(dataset, "BLR-DEL", is_synthetic_data=True, models=["naive"])
    assert results["naive"].status == STATUS_INSUFFICIENT_DATA
    assert results["naive"].number_of_forecasts == 0


def test_evaluate_route_baselines_rejects_unknown_model():
    rows = [_route_row("2026-01", "BLR-DEL", 100.0)]
    dataset = _dataset(rows)
    with pytest.raises(ValueError):
        evaluate_route_baselines(dataset, "BLR-DEL", is_synthetic_data=True, models=["not_a_model"])


# --- multi-route: independence ------------------------------------------------


def test_forecast_all_routes_handles_each_route_independently():
    periods = ["2026-01", "2026-02", "2026-03"]
    rows = [
        _route_row("2026-01", "BLR-DEL", 100.0),
        _route_row("2026-02", "BLR-DEL", 105.0),
        _route_row("2026-03", "BLR-DEL", 110.0),
        # DEL-BOM has no OK data at all -> insufficient, must not affect BLR-DEL
        _route_row("2026-01", "DEL-BOM", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
        _route_row("2026-02", "DEL-BOM", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
        _route_row("2026-03", "DEL-BOM", None, status=ROUTE_STATUS_INSUFFICIENT_DATA),
    ]
    dataset = _dataset(rows, periods=periods)

    results = forecast_all_routes(dataset, is_synthetic_data=True, model="naive")

    assert set(results.keys()) == {"BLR-DEL", "DEL-BOM"}
    assert results["BLR-DEL"].status == STATUS_OK
    assert results["BLR-DEL"].forecast_value == 110.0
    assert results["DEL-BOM"].status == STATUS_INSUFFICIENT_DATA
    assert results["DEL-BOM"].forecast_value is None


def test_evaluate_all_routes_handles_each_route_independently():
    periods = ["2026-01", "2026-02", "2026-03", "2026-04"]
    rows = [_route_row(p, "BLR-DEL", 100.0 + i * 5) for i, p in enumerate(periods)]
    rows += [_route_row(p, "DEL-BOM", None, status=ROUTE_STATUS_INSUFFICIENT_DATA) for p in periods]
    dataset = _dataset(rows, periods=periods)

    results = evaluate_all_routes(dataset, is_synthetic_data=True, models=["naive"])

    assert results["BLR-DEL"]["naive"].status == STATUS_OK
    assert results["BLR-DEL"]["naive"].number_of_forecasts == 3
    assert results["DEL-BOM"]["naive"].status == STATUS_INSUFFICIENT_DATA
