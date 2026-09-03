"""Baseline forecasting models — Stage 3, gap-aware since Stage 3.1.

Deliberately simple, explainable models only: naive (persistence),
historical mean, and a short moving average. These exist to set a
statistically defensible floor that any future, more complex model
(ARIMA/ML/etc.) must outperform before it's worth adopting — they are not
intended to be the project's final forecasting solution.

Every function here takes a chronologically sorted, CALENDAR-COMPLETE
pandas Series of historical ``national_index`` values (see
``forecasting.series.national_index_series``) — meaning some entries may
be ``NaN`` for a real calendar gap, not merely a shorter series. Each
function decides for itself, explicitly, how to handle gaps:

- ``naive``/``historical_mean`` skip past a gap to use the most recent
  REAL value(s) available — this is not interpolation (no value is
  invented for the gap itself), just using genuine past observations.
- ``moving_average`` does NOT skip gaps: it requires the literal most
  recent ``window`` calendar slots to all be real. Reaching further back
  to "find" ``window`` real values elsewhere would silently redefine what
  "the last `window` months" means.

Every function returns ``None`` — never a filled-in guess — when it
cannot legitimately produce a forecast from the given history.

Deep learning, ARIMA/SARIMA, Prophet, and tree-based ML models are
explicitly out of scope for this stage — see docs/forecasting_methodology.md.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import pandas as pd


def naive_forecast(history: pd.Series) -> Optional[float]:
    """Forecast = the most recently OBSERVED (non-gap) value. Skips past
    any trailing gap to find it — using a real past observation is not
    interpolation. Needs >= 1 real (non-NaN) historical point."""
    real = history.dropna()
    if len(real) < 1:
        return None
    return float(real.iloc[-1])


def historical_mean_forecast(history: pd.Series) -> Optional[float]:
    """Forecast = the mean of every REAL (non-gap) historical value seen
    so far. Gap months contribute nothing to the mean — they are not
    counted as zero or interpolated. Needs >= 1 real historical point."""
    real = history.dropna()
    if len(real) < 1:
        return None
    return float(real.mean())


def moving_average_forecast(history: pd.Series, window: int = 3) -> Optional[float]:
    """Forecast = the mean of the last ``window`` CALENDAR-CONSECUTIVE
    values.

    Unlike ``naive``/``historical_mean``, this does NOT skip past a gap to
    find enough real points elsewhere: the literal most recent ``window``
    calendar slots must all be real (non-NaN), or this returns ``None``.
    A 2-real-plus-1-gap window under ``window=3`` is not a 2-point moving
    average wearing a different name — it's insufficient data, reported
    as such by the caller (see ``backtesting.rolling_origin_backtest``),
    not silently substituted.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if len(history) < window:
        return None
    recent_window = history.iloc[-window:]
    if recent_window.isna().any():
        return None
    return float(recent_window.mean())


#: Registry of available baseline models, keyed by the name used
#: throughout ForecastResult.model_used / ModelEvaluationResult.model.
BASELINE_MODELS: Dict[str, Callable[..., Optional[float]]] = {
    "naive": naive_forecast,
    "historical_mean": historical_mean_forecast,
    "moving_average": moving_average_forecast,
}
