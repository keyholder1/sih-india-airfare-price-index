"""Real MoSPI PLFS wage/earnings series, reshaped into the monthly income
series `index_engine.affordability.calculate_affordability` expects.

The underlying data is REAL (see data/benchmarks/mospi_income_README.md
for full provenance and retrieval details) but published only annually --
there is no real monthly Indian wage series available anywhere. Rather
than fabricate monthly movement that was never measured, every month
within a calendar year is assigned that year's single real value, held
flat. This means the resulting affordability index only genuinely moves
once a year even though it is queried monthly; that is an honest
reflection of how often the real statistic changes, not a limitation of
this module to hide.

Kept independent of the live MoSPI API: this module reads the committed,
already-retrieved CSV snapshot, the same pattern
analytics_service.get_forecast() uses for the MoSPI CPI benchmark
(data/benchmarks/cpi_1337.xlsx) -- a live API call on every dashboard
request would be slow, adds an external dependency to every page load,
and the underlying statistic only changes once a year regardless.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

#: Source tag on every row -- distinct from "REAL" or "SYNTHETIC" used
#: elsewhere in this project, because neither alone is honest here: the
#: underlying value is genuinely real, but held flat across months it
#: was never measured for. Never collapse this into a plain "real" label.
SOURCE_TAG = "MOSPI_PLFS_ANNUAL_HELD_FLAT"

INCOME_INDICATOR = "income_index"


def load_mospi_income_series(csv_path: Path) -> pd.DataFrame:
    """Read the committed MoSPI PLFS snapshot and expand it into one row
    per (period=YYYY-MM, indicator, value, source) -- the shape
    affordability.calculate_affordability requires -- by holding each
    year's single real value flat across that year's 12 months.

    Returns an empty-but-correctly-shaped DataFrame if the file is
    missing, so a caller can treat "no income data" the same way
    affordability.py already does (STATUS_DATA_UNAVAILABLE), rather than
    raising.
    """
    columns = ["period", "indicator", "value", "source"]
    if not csv_path.exists():
        return pd.DataFrame(columns=columns)

    annual = pd.read_csv(csv_path)
    rows = []
    for _, row in annual.iterrows():
        year = int(row["year"])
        value = float(row["value"])
        for month in range(1, 13):
            rows.append(
                {
                    "period": f"{year:04d}-{month:02d}",
                    "indicator": INCOME_INDICATOR,
                    "value": value,
                    "source": SOURCE_TAG,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def default_mospi_income_path(repo_root: Path) -> Path:
    return repo_root / "data" / "benchmarks" / "mospi_plfs_income.csv"
