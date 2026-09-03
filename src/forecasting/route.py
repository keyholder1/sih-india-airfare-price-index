"""Route-level baseline forecasting.

Applies the exact same architecture and safeguards as
``forecasting.national`` — calendar-aware baseline models, leak-free
rolling-origin backtesting, explicit status fields, no fabricated
values — to one route's history instead of the national aggregate. No
model, backtesting, or index/aggregation logic is duplicated here: this
module only calls the same generic ``forecasting.baseline_models`` /
``forecasting.backtesting`` functions ``national.py`` already uses, fed a
route's calendar-complete series (``forecasting.series.route_index_series``)
instead of the national one.

``forecast_route_index`` / ``evaluate_route_baselines`` mirror
``forecast_national_index`` / ``evaluate_national_baselines`` field for
field and behavior for behavior (see those functions' docstrings — not
repeated here). ``forecast_all_routes`` / ``evaluate_all_routes`` are thin
convenience wrappers running the single-route functions across every
route in the dataset; a route with insufficient history reports
``STATUS_INSUFFICIENT_DATA`` in its own result exactly as
``forecast_route_index`` already would in isolation — one route's thin
history never prevents another route's result from being produced.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
from index_engine.utils import shift_period

from forecasting.backtesting import rolling_origin_backtest
from forecasting.baseline_models import BASELINE_MODELS
from forecasting.data_access import ForecastingDataset
from forecasting.results import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MODEL_NOT_APPLICABLE,
    STATUS_OK,
    ForecastResult,
    ModelEvaluationResult,
)
from forecasting.series import route_index_series

#: Same threshold as forecasting.national — see that module for rationale.
MIN_FOLDS_FOR_INTERVAL = 3


def forecast_route_index(
    dataset: ForecastingDataset,
    route: str,
    is_synthetic_data: bool,
    model: str = "naive",
    horizon: int = 1,
    window: int = 3,
) -> ForecastResult:
    """Produce ONE forecast for the period immediately after the last real
    (non-gap) period in ``route``'s history. Identical contract and
    behavior to ``forecasting.national.forecast_national_index`` — see
    that function's docstring for the full explanation of gap handling,
    the ``horizon``/``is_synthetic_data`` requirements, and how the
    prediction interval is derived — applied here to one route's series
    instead of the national one.

    Raises
    ------
    ValueError
        If ``route`` is unknown (see ``route_index_series``), ``model``
        is not a key in ``BASELINE_MODELS``, or ``horizon != 1``.
    """
    if horizon != 1:
        raise ValueError(
            "This stage only supports horizon=1 (one month ahead), matching "
            "forecasting.national.forecast_national_index."
        )
    if model not in BASELINE_MODELS:
        raise ValueError(f"Unknown model {model!r}. Available: {sorted(BASELINE_MODELS)}")

    series = route_index_series(dataset, route)
    model_fn = BASELINE_MODELS[model]
    kwargs = {"window": window} if model == "moving_average" else {}

    real = series.dropna()
    if real.empty:
        return ForecastResult(
            forecast_period="UNKNOWN",
            forecast_value=None,
            model_used=model,
            horizon=horizon,
            training_period=list(series.index),
            data_points_used=0,
            lower_bound=None,
            upper_bound=None,
            status=STATUS_INSUFFICIENT_DATA,
            is_synthetic_data=is_synthetic_data,
            notes=(
                f"No historical route_index values available for route {route!r} to forecast from "
                "(every period missing, or the route was never OK)."
            ),
        )

    last_real_period = real.index[-1]
    forecast_period = shift_period(last_real_period, horizon)

    forecast_value = model_fn(series, **kwargs)
    data_points_used = int(series.notna().sum())

    if forecast_value is None:
        return ForecastResult(
            forecast_period=forecast_period,
            forecast_value=None,
            model_used=model,
            horizon=horizon,
            training_period=list(series.index),
            data_points_used=data_points_used,
            lower_bound=None,
            upper_bound=None,
            status=STATUS_MODEL_NOT_APPLICABLE,
            is_synthetic_data=is_synthetic_data,
            notes=f"{model} could not produce a forecast for route {route!r} from {data_points_used} real point(s).",
        )

    lower_bound = upper_bound = None
    evaluation = rolling_origin_backtest(series, model_fn, model, is_synthetic_data=is_synthetic_data, **kwargs)
    backtest_errors = [
        series[f.forecast_period] - f.forecast_value for f in evaluation.forecasts if f.status == STATUS_OK
    ]

    if len(backtest_errors) >= MIN_FOLDS_FOR_INTERVAL:
        std = pd.Series(backtest_errors).std(ddof=1)
        if std is not None and not pd.isna(std):
            lower_bound = forecast_value - 1.96 * std
            upper_bound = forecast_value + 1.96 * std
            interval_note = (
                f"Rough ~95% interval from {len(backtest_errors)} backtest residuals (normal "
                "approximation) — not a statistically rigorous prediction interval; treat as illustrative."
            )
        else:
            interval_note = "Backtest residual standard deviation could not be computed (degenerate case)."
    else:
        interval_note = (
            f"No confidence interval computed: only {len(backtest_errors)} scored backtest residual(s) "
            f"available (need >= {MIN_FOLDS_FOR_INTERVAL} for even a rough empirical interval)."
        )

    return ForecastResult(
        forecast_period=forecast_period,
        forecast_value=forecast_value,
        model_used=model,
        horizon=horizon,
        training_period=list(series.index),
        data_points_used=data_points_used,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        status=STATUS_OK,
        is_synthetic_data=is_synthetic_data,
        notes=interval_note,
    )


def evaluate_route_baselines(
    dataset: ForecastingDataset,
    route: str,
    is_synthetic_data: bool,
    models: Optional[List[str]] = None,
    min_train_size: int = 1,
    window: int = 3,
) -> Dict[str, ModelEvaluationResult]:
    """Rolling-origin backtest every requested baseline model (default:
    all of ``BASELINE_MODELS``) against ``route``'s ``route_index``
    history. Identical contract to
    ``forecasting.national.evaluate_national_baselines`` — see that
    function's docstring — applied to one route's series.
    """
    unknown_models = [name for name in (models or []) if name not in BASELINE_MODELS]
    if unknown_models:
        raise ValueError(f"Unknown model(s) {unknown_models}. Available: {sorted(BASELINE_MODELS)}")

    series = route_index_series(dataset, route)
    models = models if models is not None else list(BASELINE_MODELS)
    results: Dict[str, ModelEvaluationResult] = {}
    for name in models:
        model_fn = BASELINE_MODELS[name]
        kwargs = {"window": window} if name == "moving_average" else {}
        results[name] = rolling_origin_backtest(
            series,
            model_fn,
            name,
            is_synthetic_data=is_synthetic_data,
            min_train_size=min_train_size,
            **kwargs,
        )
    return results


def forecast_all_routes(
    dataset: ForecastingDataset,
    is_synthetic_data: bool,
    model: str = "naive",
    horizon: int = 1,
    window: int = 3,
) -> Dict[str, ForecastResult]:
    """``forecast_route_index`` for every route in ``dataset.route_list()``,
    keyed by route. Each route is handled independently — a route with
    insufficient history reports ``STATUS_INSUFFICIENT_DATA`` in its own
    entry exactly as calling ``forecast_route_index`` for it alone would;
    it never prevents another route's entry from being produced.
    """
    return {
        route: forecast_route_index(dataset, route, is_synthetic_data, model=model, horizon=horizon, window=window)
        for route in dataset.route_list()
    }


def evaluate_all_routes(
    dataset: ForecastingDataset,
    is_synthetic_data: bool,
    models: Optional[List[str]] = None,
    min_train_size: int = 1,
    window: int = 3,
) -> Dict[str, Dict[str, ModelEvaluationResult]]:
    """``evaluate_route_baselines`` for every route in
    ``dataset.route_list()``, keyed by route. Same independence guarantee
    as ``forecast_all_routes``.
    """
    return {
        route: evaluate_route_baselines(
            dataset, route, is_synthetic_data, models=models, min_train_size=min_train_size, window=window
        )
        for route in dataset.route_list()
    }
