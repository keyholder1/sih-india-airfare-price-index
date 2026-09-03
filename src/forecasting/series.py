"""Turns a ForecastingDataset's national table into a clean, CALENDAR-
COMPLETE pandas Series suitable for baseline forecasting and backtesting.

Stage 3.1 fix: earlier, this module dropped every period where
``national_index`` was ``None``, producing an array-position-indexed
Series with no way to tell a real 1-month gap from a 3-month one. Any
positional operation downstream (backtesting fold construction, MASE's
in-sample scale, moving-average windows) then silently treated
non-adjacent calendar months as adjacent.

The fix: preserve every period in ``dataset.periods`` — the same
calendar-complete range Stage 1 already builds — with ``NaN`` standing in
for "no trustworthy value here," never a dropped row. Position ``k`` in
the resulting Series is now guaranteed to be exactly one calendar month
after position ``k-1``, which is what lets ``backtesting.py`` reason about
real elapsed time using simple positional indexing plus an explicit
``shift_period``-based contiguity guard.

Nothing is interpolated or fabricated: NaN always means "no trustworthy
value," never a guess.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from forecasting.data_access import ForecastingDataset
from forecasting.dtypes import to_numeric_safe


def national_index_series(
    dataset: ForecastingDataset,
    min_coverage_rate: Optional[float] = None,
) -> pd.Series:
    """Chronologically sorted, calendar-complete pandas Series of
    ``national_index`` values, indexed by every period in
    ``dataset.periods`` (in order) — including periods index_engine could
    not compute a value for (``NaN``), and, if ``min_coverage_rate`` is
    set, periods whose numeric value exists but whose ``coverage_rate``
    falls below that threshold (also treated as ``NaN``).

    Parameters
    ----------
    min_coverage_rate:
        ``None`` (the default) applies no additional filtering beyond
        what index_engine itself already computed — every period with a
        non-``None`` ``national_index`` is kept as-is. If set, any period
        whose ``coverage_rate`` is below this threshold is treated as
        missing (``NaN``) for forecasting purposes, even though
        index_engine did produce a numeric ``national_index`` for it.

        This is never applied silently: passing a threshold changes what
        the training/backtesting sample considers "trustworthy," and is
        an explicit, deliberate choice for the caller to make — the
        default is "trust every value index_engine itself was willing to
        compute," not some assumed minimum quality bar.
    """
    df = dataset.national.set_index("period").reindex(dataset.periods)

    values = to_numeric_safe(df["national_index"])

    if min_coverage_rate is not None:
        coverage = to_numeric_safe(df["coverage_rate"])
        below_threshold = (coverage < min_coverage_rate).fillna(False)
        values = values.mask(below_threshold)

    return pd.Series(values.to_numpy(dtype=float), index=pd.Index(dataset.periods, name="period"))


def route_index_series(dataset: ForecastingDataset, route: str) -> pd.Series:
    """Chronologically sorted, calendar-complete pandas Series of
    ``route_index`` values for one route, indexed by every period in
    ``dataset.periods`` — the per-route counterpart to
    ``national_index_series``, built the same way (NaN for any period with
    no trustworthy value, never a dropped row).

    Unlike ``national_index_series``, there is no ``min_coverage_rate``
    parameter: ``coverage_rate`` is a national-level concept (the fraction
    of ROUTES covered in a period) with no column on ``ROUTE_COLUMNS``.
    index_engine already leaves ``route_index`` as ``None`` for any period
    where a route's own status isn't OK (NEW_ROUTE / DISCONTINUED /
    INSUFFICIENT_DATA / NO_BASE_DATA — see ``ForecastingDataset``'s
    docstring), so that status is already this series' quality signal —
    nothing further to filter here.

    Raises
    ------
    ValueError
        If ``route`` does not appear anywhere in ``dataset.routes`` — an
        unknown/typo'd route name is a caller error, kept distinct from a
        real route that legitimately has no OK periods (which instead
        produces an all-``NaN`` series, same as any other genuine gap).
    """
    if route not in set(dataset.routes["route"]):
        raise ValueError(f"Unknown route {route!r}. Known routes: {dataset.route_list()}")

    df = dataset.routes[dataset.routes["route"] == route].set_index("period").reindex(dataset.periods)
    values = to_numeric_safe(df["route_index"])
    return pd.Series(values.to_numpy(dtype=float), index=pd.Index(dataset.periods, name="period"))
