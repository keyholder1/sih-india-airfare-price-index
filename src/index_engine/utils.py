"""Small shared helpers."""

from __future__ import annotations

import pandas as pd


def shift_period(period: str, months: int) -> str:
    """Shift a ``YYYY-MM`` period string by ``months`` (may be negative)."""
    ts = pd.Timestamp(period + "-01") + pd.DateOffset(months=months)
    return ts.strftime("%Y-%m")


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        raise ZeroDivisionError("Cannot compute percent change from a zero base value")
    return (current / previous - 1.0) * 100.0
