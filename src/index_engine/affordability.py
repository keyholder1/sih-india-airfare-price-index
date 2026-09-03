"""Relative Airfare Affordability Index.

Answers a narrower question than it might sound like: did airfare rise
faster or slower than a chosen income/wage indicator? It is NOT a real
household-affordability metric unless the income data behind it is real,
validated income data — this module never fabricates that data itself.

    Relative Affordability Index = (Airfare Index / Income Index) x 100

Example: Airfare Index 110, Income Index 105 -> 104.76, read as "the
relative airfare burden rose about 4.76% relative to this income
indicator" — not as "average households can afford 4.76% less air travel."

If no income data is supplied for the requested period, the result status
is DATA_UNAVAILABLE and no number is invented. The core AirfarePriceIndex
works completely independently of this module — affordability is always
optional.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

STATUS_OK = "OK"
STATUS_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

INCOME_INPUT_COLUMNS = ("period", "indicator", "value", "source")


@dataclass
class AffordabilityResult:
    period: str
    indicator: Optional[str]
    airfare_index: Optional[float]
    income_index: Optional[float]
    relative_affordability_index: Optional[float]
    status: str
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def validate_income_series(income_series: pd.DataFrame) -> None:
    missing = [c for c in ("period", "indicator", "value") if c not in income_series.columns]
    if missing:
        raise ValueError(f"Income series is missing required columns: {missing}")


def calculate_affordability(
    airfare_index: Optional[float],
    period: str,
    income_series: Optional[pd.DataFrame],
    indicator: str = "income_index",
) -> AffordabilityResult:
    """``income_series`` has columns period, indicator, value[, source] — see
    INCOME_INPUT_COLUMNS. Pass ``None`` (or an empty frame) when no income
    data is available; the core index still works without it."""
    if airfare_index is None or income_series is None or income_series.empty:
        return AffordabilityResult(period, indicator, airfare_index, None, None, STATUS_DATA_UNAVAILABLE)

    validate_income_series(income_series)
    match = income_series[(income_series["period"] == period) & (income_series["indicator"] == indicator)]
    if match.empty:
        return AffordabilityResult(period, indicator, airfare_index, None, None, STATUS_DATA_UNAVAILABLE)

    income_index = float(match["value"].iloc[0])
    if income_index == 0:
        return AffordabilityResult(period, indicator, airfare_index, None, None, STATUS_DATA_UNAVAILABLE)

    relative = (airfare_index / income_index) * 100.0
    source = match["source"].iloc[0] if "source" in match.columns and not match["source"].isna().all() else None
    return AffordabilityResult(period, indicator, airfare_index, income_index, relative, STATUS_OK, source)
