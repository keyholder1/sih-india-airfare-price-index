"""Rolling-origin (walk-forward) backtesting for baseline models — Stage 3,
calendar-aware since Stage 3.1.

No future data is ever used to produce a past forecast: at split ``k``,
only periods ``series.iloc[:k]`` are visible to the model, and it is
evaluated against period ``k + horizon - 1``.

Stage 3.1 fix: this function now REQUIRES a calendar-complete series (see
``forecasting.series.national_index_series``) — one entry per real
calendar period, with ``NaN`` standing in for a missing/filtered period,
never a dropped row. This is what lets position-based indexing correctly
correspond to real elapsed calendar time. An explicit contiguity guard
(built on index_engine's own ``shift_period``) raises immediately if a
non-calendar-complete series is ever passed in, rather than silently
mislabeling a fold's horizon.

Two distinct "nothing to score" cases are now reported separately:

- The TARGET period itself has no trustworthy value (missing/filtered) —
  the fold is skipped with status TARGET_UNAVAILABLE. Nothing about the
  model is at fault here; there's simply no ground truth to compare against.
- The model can't produce a forecast from the training window (e.g. a
  moving-average window not yet fully real) — status MODEL_NOT_APPLICABLE,
  as before.

Neither case is counted as an error, and neither is silently absorbed
into MAE/RMSE/MASE.

Example (min_train_size=1, horizon=1), matching the walk-forward pattern
requested for this stage:

    train=[Jan]                 -> predict Feb
    train=[Jan, Feb]            -> predict Mar
    train=[Jan, Feb, Mar]       -> predict Apr
    ...
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional

import pandas as pd
from index_engine.utils import shift_period

from forecasting.results import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_MODEL_NOT_APPLICABLE,
    STATUS_OK,
    STATUS_TARGET_UNAVAILABLE,
    ForecastResult,
    ModelEvaluationResult,
)

ModelFn = Callable[..., Optional[float]]

#: Below this many usable backtest folds, MAE/RMSE/MASE are reported but
#: flagged as illustrative rather than statistically reliable — see
#: docs/forecasting_methodology.md.
RELIABLE_FOLD_COUNT = 3


def _one_step_naive_in_sample_mae(train: pd.Series) -> Optional[float]:
    """In-sample one-step naive MAE of ``train``, used as MASE's scale
    denominator (Hyndman & Koehler's definition).

    Gap-safe by construction: ``pd.Series.diff()`` produces NaN wherever
    either side of a pairwise difference is NaN, and ``dropna()`` removes
    those — so a difference spanning a gap (i.e. NOT a genuine one-step
    calendar difference) is correctly excluded rather than mistakenly
    treated as adjacent. Needs >= 2 points (real or not) to have even one
    diff; returns ``None`` (never 0 or a fabricated value) if no genuine
    one-step diff survives.
    """
    if len(train) < 2:
        return None
    diffs = train.diff().dropna().abs()
    if diffs.empty:
        return None
    scale = float(diffs.mean())
    return scale if scale != 0 else None


def rolling_origin_backtest(
    series: pd.Series,
    model_fn: ModelFn,
    model_name: str,
    is_synthetic_data: bool,
    min_train_size: int = 1,
    horizon: int = 1,
    **model_kwargs,
) -> ModelEvaluationResult:
    """Walk-forward, one-step-ahead-by-default backtest of ``model_fn``
    over ``series``.

    Parameters
    ----------
    series:
        A CALENDAR-COMPLETE, chronologically sorted series — see
        ``forecasting.series.national_index_series``. Every calendar
        period in the intended range must have an entry (NaN for
        missing/filtered periods), never a dropped row. Passing a series
        with rows removed for missing periods will trigger the
        contiguity guard below.
    model_fn:
        One of ``forecasting.baseline_models.BASELINE_MODELS``, or any
        callable with the same ``(history, **kwargs) -> Optional[float]``
        signature. Receives the full (possibly gap-containing) training
        window and decides its own gap policy — see baseline_models.py.
    is_synthetic_data:
        REQUIRED, no default — the caller must state explicitly whether
        ``series`` was built from synthetic or real fare data, the same
        explicit-over-implicit convention used by
        ``forecasting.cpi_benchmark.compare_to_mospi_cpi``'s
        ``is_synthetic_airfare_data``. This is never silently assumed.
    min_train_size:
        Smallest training window (in calendar positions) to attempt.
        Must be >= 1. Default 1, matching the walk-forward pattern in
        this module's docstring.
    horizon:
        Calendar periods ahead each fold predicts. Default 1.

    Raises
    ------
    ValueError
        If ``min_train_size < 1`` — validated explicitly, before any fold
        is constructed, so a misuse here can never be masked by Python's
        negative-indexing wraparound producing a confusing
        "calendar-contiguity violated" error instead of a clear one.
    ValueError
        If ``series`` is not calendar-complete (the contiguity guard
        fails) — this indicates a caller passed in a non-calendar-complete
        series, a programming error this function refuses to silently
        mislabel.
    """
    if min_train_size < 1:
        raise ValueError(f"min_train_size must be >= 1, got {min_train_size}")

    n = len(series)
    forecasts: List[ForecastResult] = []
    errors: List[float] = []
    mase_terms: List[float] = []
    skipped_model_not_applicable = 0
    skipped_target_unavailable = 0

    for k in range(min_train_size, n - horizon + 1):
        train = series.iloc[:k]
        target_idx = k + horizon - 1
        target_period = series.index[target_idx]
        data_points_used = int(train.notna().sum())

        # Explicit calendar-contiguity guard. With a genuinely
        # calendar-complete series this can only ever pass — it exists to
        # catch a caller passing in a series with gap rows removed
        # (exactly the Stage 3.1 bug this fix addresses), rather than
        # silently mislabeling a multi-month gap as horizon=1.
        last_train_period = series.index[k - 1]
        expected_target_period = shift_period(last_train_period, horizon)
        if expected_target_period != target_period:
            raise ValueError(
                f"Calendar-contiguity violated: training ends at {last_train_period!r}, horizon={horizon} "
                f"implies target {expected_target_period!r}, but the series' next position is "
                f"{target_period!r} instead. rolling_origin_backtest requires a calendar-complete series "
                "(see forecasting.series.national_index_series) — every calendar period present in "
                "sequence, with gaps represented as NaN, never as omitted rows."
            )

        actual = series.iloc[target_idx]

        if pd.isna(actual):
            skipped_target_unavailable += 1
            forecasts.append(
                ForecastResult(
                    forecast_period=target_period,
                    forecast_value=None,
                    model_used=model_name,
                    horizon=horizon,
                    training_period=list(train.index),
                    data_points_used=data_points_used,
                    lower_bound=None,
                    upper_bound=None,
                    status=STATUS_TARGET_UNAVAILABLE,
                    is_synthetic_data=is_synthetic_data,
                    notes=(
                        f"Target period {target_period} has no trustworthy national_index value "
                        "(missing or filtered by a quality threshold) — skipped, not scored."
                    ),
                )
            )
            continue

        forecast_value = model_fn(train, **model_kwargs)

        if forecast_value is None:
            skipped_model_not_applicable += 1
            forecasts.append(
                ForecastResult(
                    forecast_period=target_period,
                    forecast_value=None,
                    model_used=model_name,
                    horizon=horizon,
                    training_period=list(train.index),
                    data_points_used=data_points_used,
                    lower_bound=None,
                    upper_bound=None,
                    status=STATUS_MODEL_NOT_APPLICABLE,
                    is_synthetic_data=is_synthetic_data,
                    notes=(
                        f"{model_name} could not produce a forecast from {data_points_used} real "
                        f"(non-gap) point(s) out of {len(train)} calendar period(s) in the training window."
                    ),
                )
            )
            continue

        error = actual - forecast_value
        errors.append(error)

        scale = _one_step_naive_in_sample_mae(train)
        if scale is not None:
            mase_terms.append(abs(error) / scale)

        forecasts.append(
            ForecastResult(
                forecast_period=target_period,
                forecast_value=forecast_value,
                model_used=model_name,
                horizon=horizon,
                training_period=list(train.index),
                data_points_used=data_points_used,
                lower_bound=None,
                upper_bound=None,
                status=STATUS_OK,
                is_synthetic_data=is_synthetic_data,
                notes=None,
            )
        )

    number_of_forecasts = len(errors)
    total_skipped = skipped_model_not_applicable + skipped_target_unavailable

    if number_of_forecasts == 0:
        return ModelEvaluationResult(
            model=model_name,
            number_of_forecasts=0,
            mae=None,
            rmse=None,
            mase=None,
            mase_status="No backtest fold produced a scored forecast — insufficient history for this model.",
            status=STATUS_INSUFFICIENT_DATA,
            notes=(
                f"{total_skipped} fold(s) attempted, all skipped "
                f"({skipped_target_unavailable} target-unavailable, {skipped_model_not_applicable} model-not-applicable). "
                "The series is too short, or too gap-heavy, for this model's requirements."
            ),
            forecasts=forecasts,
        )

    mae = float(sum(abs(e) for e in errors) / number_of_forecasts)
    rmse = float(math.sqrt(sum(e**2 for e in errors) / number_of_forecasts))

    if mase_terms:
        mase = float(sum(mase_terms) / len(mase_terms))
        if len(mase_terms) < number_of_forecasts:
            mase_status = (
                f"Computed from {len(mase_terms)} of {number_of_forecasts} fold(s); folds without a "
                "genuine one-step-adjacent in-sample naive scale (e.g. a 1-point training window, or a "
                "gap immediately preceding it) were excluded."
            )
        else:
            mase_status = f"Computed from all {len(mase_terms)} fold(s)."
    else:
        mase = None
        mase_status = (
            "MASE could not be computed: no backtest fold had a genuine one-step-adjacent in-sample "
            "naive scale available."
        )

    notes_parts = []
    if skipped_target_unavailable:
        notes_parts.append(
            f"{skipped_target_unavailable} fold(s) skipped because the target period had no trustworthy "
            "value (missing or filtered) — excluded, not scored as errors."
        )
    if skipped_model_not_applicable:
        notes_parts.append(
            f"{skipped_model_not_applicable} fold(s) skipped for this model (its data requirement, e.g. "
            "a moving-average window not fully real, was not met) — excluded, not scored as errors."
        )
    if number_of_forecasts < RELIABLE_FOLD_COUNT:
        notes_parts.append(
            f"Only {number_of_forecasts} backtest fold(s) available — with a series this short, these "
            "metrics are illustrative, not statistically reliable evidence of model accuracy."
        )

    return ModelEvaluationResult(
        model=model_name,
        number_of_forecasts=number_of_forecasts,
        mae=mae,
        rmse=rmse,
        mase=mase,
        mase_status=mase_status,
        status=STATUS_OK,
        notes=" ".join(notes_parts) if notes_parts else None,
        forecasts=forecasts,
    )
