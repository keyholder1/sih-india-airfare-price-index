"""Loader for MoSPI's official CPI Airfare sub-index (``cpi_1337.xlsx``).

This module only parses the source extract into a clean, period-indexed
structure. It does not compute any comparison, does not touch
``index_engine`` or ``data_quality``, and does not interpret or reject
values beyond basic schema/parse checks (fail loud on a genuinely
malformed file, never guess).

Source schema (as delivered): one row per month, columns
``base_year, series, year, month, state, sector, division, group, class,
sub_class, item, code, index, inflation, imputation``. ``month`` is a full
month name (e.g. "January"), not numeric — there is no combined period
column in the source file, so one is constructed here. ``base_year``,
``series``, ``state``, ``sector``, and the classification columns are
constant across every row in the extract; they are preserved as
provenance metadata, not repeated per-period fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import pandas as pd

MONTH_NAME_TO_NUMBER: Dict[str, int] = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

REQUIRED_COLUMNS = ("year", "month", "index", "inflation", "imputation", "base_year")

#: Value in the source ``imputation`` column meaning "not imputed". Any
#: other value (case-insensitive) is treated as imputed.
_NOT_IMPUTED_VALUE = "N"


@dataclass
class MospiCpiSeries:
    """Parsed MoSPI CPI Airfare series, one value per period.

    ``yoy_inflation_by_period`` is MoSPI's own year-over-year figure, as
    published — not recomputed or altered here. It is ``None`` for any
    period the source extract itself left blank (no 12-months-prior data
    within the extract), matching the source exactly rather than
    back-filling anything.

    ``imputed_by_period`` is a straight pass-through of the source
    ``imputation`` column, kept deliberately separate from any of this
    project's own data-quality signals (see docs/data_quality.md and
    cpi_benchmark.py's module docstring for why these are never merged).
    """

    periods: List[str]
    index_by_period: Dict[str, float]
    yoy_inflation_by_period: Dict[str, Optional[float]]
    imputed_by_period: Dict[str, bool]
    base_year: int
    item: str
    state: str
    sector: str
    source_file: str

    def index_series(self) -> pd.Series:
        """Chronologically ordered pandas Series of the raw (not rebased)
        index values, indexed by period string."""
        return pd.Series(
            [self.index_by_period[p] for p in self.periods],
            index=pd.Index(self.periods, name="period"),
            dtype=float,
        )

    def to_dict(self) -> dict:
        return {
            "periods": self.periods,
            "index_by_period": self.index_by_period,
            "yoy_inflation_by_period": self.yoy_inflation_by_period,
            "imputed_by_period": self.imputed_by_period,
            "base_year": self.base_year,
            "item": self.item,
            "state": self.state,
            "sector": self.sector,
            "source_file": self.source_file,
        }


def load_mospi_cpi_series(
    path: Union[str, "os.PathLike"],
    sheet_name: Optional[str] = None,
) -> MospiCpiSeries:
    """Load and parse a MoSPI CPI extract (``cpi_1337.xlsx`` shape).

    Parameters
    ----------
    path:
        Path to the ``.xlsx`` file.
    sheet_name:
        Optional explicit sheet name. If omitted, the first sheet is used.

    Raises
    ------
    ValueError
        If required columns are missing, a month name doesn't parse, or
        the extract contains duplicate periods — fail loud rather than
        silently dropping or guessing.
    """
    raw = pd.read_excel(path, sheet_name=sheet_name if sheet_name is not None else 0)

    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"{path}: missing required column(s): {missing}")

    work = raw.copy()
    month_numbers = work["month"].astype(str).str.strip().map(MONTH_NAME_TO_NUMBER)
    unparseable_mask = month_numbers.isna()
    if unparseable_mask.any():
        bad_values = sorted(work.loc[unparseable_mask, "month"].astype(str).unique().tolist())
        raise ValueError(f"{path}: unrecognized month name(s): {bad_values}")

    work["period"] = (
        work["year"].astype(int).astype(str) + "-" + month_numbers.astype(int).astype(str).str.zfill(2)
    )
    work = work.sort_values("period").reset_index(drop=True)

    duplicate_periods = sorted(work.loc[work["period"].duplicated(), "period"].unique().tolist())
    if duplicate_periods:
        raise ValueError(f"{path}: duplicate period(s): {duplicate_periods}")

    base_years = work["base_year"].unique()
    if len(base_years) != 1:
        raise ValueError(f"{path}: expected a single base_year, found: {sorted(base_years.tolist())}")

    index_by_period = {p: float(v) for p, v in zip(work["period"], work["index"])}
    yoy_inflation_by_period = {
        p: (float(v) if pd.notna(v) else None) for p, v in zip(work["period"], work["inflation"])
    }
    imputed_by_period = {
        p: (str(v).strip().upper() != _NOT_IMPUTED_VALUE) for p, v in zip(work["period"], work["imputation"])
    }

    return MospiCpiSeries(
        periods=list(work["period"]),
        index_by_period=index_by_period,
        yoy_inflation_by_period=yoy_inflation_by_period,
        imputed_by_period=imputed_by_period,
        base_year=int(base_years[0]),
        item=str(work["item"].iloc[0]) if "item" in work.columns else "Airfare",
        state=str(work["state"].iloc[0]) if "state" in work.columns else "All India",
        sector=str(work["sector"].iloc[0]) if "sector" in work.columns else "Combined",
        source_file=str(path),
    )
