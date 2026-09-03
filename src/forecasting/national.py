"""National-level baseline forecasting — Stage 3 entry point, calendar-
aware since Stage 3.1.

Ties together: ForecastingDataset -> baseline model -> (optional) rolling-
origin backtest -> ForecastResult / ModelEvaluationResult. This is the
only module a caller (e.g. a future dashboard integration) needs for
national-level forecasting at this stage.

Route-level forecasting is explicitly out of scope for this stage — see
docs/forecasting_methodology.md.
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
from forecasting.series import national_index_series

#: Minimum number of backtest residuals required before even a rough,
#: empirical prediction interval is offered. Below this, bounds are None.
MIN_FOLDS_FOR_INTERVAL = 3


def forecast_national_index(
    dataset: ForecastingDataset,
    is_synthetic_data: bool,
    model: str = "naive",
    horizon: int = 1,
    window: int = 3,
    min_coverage_rate: Optional[float] = None,
) -> ForecastResult:
    """Produce ONE forecast for the period immediately after the LAST
    REAL (non-gap) period in the dataset's national history, using the
    requested baseline model.

    If the most recent calendar period in the dataset happens to be a
    gap itself (e.g. this month's data hasn't fully arrived), the
    forecast is anchored to the last period that actually has a
    trustworthy value, not to the literal last calendar slot — "predict
    one month past the last thing we actually know" is the well-defined
    question; "predict one month past a period we have no data for
    either" is not.

    This forecasts a genuinely unobserved (or currently-missing) period.
    For backtested, against-known-history evaluation, use
    :func:`evaluate_national_baselines` instead — the two are
    deliberately kept separate.

    ``is_synthetic_data``: REQUIRED, no default — the caller must state
    explicitly whether ``dataset`` was built from synthetic or real fare
    data, the same explicit-over-implicit convention used by
    ``forecasting.cpi_benchmark.compare_to_mospi_cpi``'s
    ``is_synthetic_airfare_data``. Never silently assumed.

    ``horizon`` must be exactly 1 in this stage: multi-step baseline
    forecasting is out of scope until the single-step baselines are
    validated on real data.

    ``min_coverage_rate``: see ``forecasting.series.national_index_series``
    — ``None`` (default) applies no additional quality filtering.
    """
    if horizon != 1:
        raise ValueError(
            "This stage only supports horizon=1 (one month ahead). Multi-step forecasting is "
            "out of scope until the single-step baselines are validated on real data."
        )
    if model not in BASELINE_MODELS:
        raise ValueError(f"Unknown model {model!r}. Available: {sorted(BASELINE_MODELS)}")

    series = national_index_series(dataset, min_coverage_rate=min_coverage_rate)
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
            notes="No historical national_index values available to forecast from (all periods missing or filtered).",
        )

    last_real_period = real.index[-1]
    forecast_period = shift_period(last_real_period, horizon)

    # The model sees the FULL calendar-complete series (with any internal
    # gaps) and applies its own gap-handling policy — see baseline_models.py.
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
            notes=f"{model} could not produce a forecast from {data_points_used} real point(s).",
        )

    # Prediction interval: only from genuine backtest residuals (STATUS_OK
    # folds only — never a fold that was skipped for missing target or
    # inapplicable model), and only when there are enough of them.
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


def evaluate_national_baselines(
    dataset: ForecastingDataset,
    is_synthetic_data: bool,
    models: Optional[List[str]] = None,
    min_train_size: int = 1,
    window: int = 3,
    min_coverage_rate: Optional[float] = None,
) -> Dict[str, ModelEvaluationResult]:
    """Rolling-origin backtest every requested baseline model (default:
    all of ``BASELINE_MODELS``) against the dataset's national_index
    history. Returns one ``ModelEvaluationResult`` per model, keyed by
    model name.

    ``is_synthetic_data``: REQUIRED, no default — see
    :func:`forecast_national_index`'s docstring for why.

    ``models``: if supplied, every name must be a key in
    ``BASELINE_MODELS`` — an unknown name raises ``ValueError`` naming
    the offending model, the same validation
    :func:`forecast_national_index` already applies to its single
    ``model`` argument.

    ``min_coverage_rate``: see ``forecasting.series.national_index_series``.
    """
    unknown_models = [name for name in (models or []) if name not in BASELINE_MODELS]
    if unknown_models:
        raise ValueError(f"Unknown model(s) {unknown_models}. Available: {sorted(BASELINE_MODELS)}")

    series = national_index_series(dataset, min_coverage_rate=min_coverage_rate)
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
