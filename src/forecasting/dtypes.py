"""Numeric dtype safety helpers.

Several columns produced by Stage 1 (e.g. ``yoy_change_pct``,
``traffic_weight``) can be entirely ``None`` in the current synthetic
sample — no YoY history exists yet, and default synthetic route weights
carry no DGCA ``traffic_weight``. pandas infers ``object`` dtype for an
all-``None`` column, not ``float64`` — silently different from what a
normal numeric column looks like, and a landmine for any code that
assumes ``float64`` without checking.

Any forecasting code that consumes one of these (or any other
Stage-1-produced numeric) column numerically should go through
:func:`to_numeric_safe` rather than assuming the dtype pandas happened to
infer.
"""

from __future__ import annotations

import pandas as pd


def to_numeric_safe(series: pd.Series) -> pd.Series:
    """Coerce ``series`` to numeric (float64), turning unparseable or
    ``None``/``NaN`` values into ``NaN`` rather than raising or silently
    leaving them as ``object`` dtype. Never fabricates a value — anything
    that was missing or unparseable stays missing."""
    return pd.to_numeric(series, errors="coerce")
