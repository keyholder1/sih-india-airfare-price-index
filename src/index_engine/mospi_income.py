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

Two distinct provenance tags come out of this, never collapsed into one:

- ``SOURCE_TAG`` (within a year that MoSPI has actually published):
  the real value for that specific year, held flat across its months.
- ``CARRIED_FORWARD_SOURCE_TAG`` (any period after the latest published
  year -- which, structurally, is every period this project's own fare
  data can ever have: the scraper only ever collects current,
  forward-looking quotes, so its periods are always at or after "now",
  while MoSPI's wage/earnings indicators lag roughly a year behind):
  the latest published year's real value, carried forward as the best
  available estimate. Same precedent already used for DGCA route
  weights (see traffic.to_engine_weights's own effective_from/to
  reasoning) -- a real, not-yet-updated number is a materially different
  thing from an invented one, and is labelled as such rather than
  presented as a fresh measurement.

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

#: Source tag for a period inside a year MoSPI has actually published --
#: distinct from "REAL" or "SYNTHETIC" used elsewhere in this project,
#: because neither alone is honest here: the underlying value is
#: genuinely real, but held flat across months it was never measured for.
SOURCE_TAG = "MOSPI_PLFS_ANNUAL_HELD_FLAT"

#: Source tag for a period after the latest year MoSPI has published --
#: the same real value as that latest year, carried forward rather than
#: reported unavailable. Never confused with a fresh measurement.
CARRIED_FORWARD_SOURCE_TAG = "MOSPI_PLFS_LATEST_CARRIED_FORWARD"

INCOME_INDICATOR = "income_index"

#: How many years past the latest real year to carry the latest value
#: forward for. Generous but bounded -- a period this far past the last
#: real publication should prompt refreshing the snapshot, not silently
#: keep serving an ever-more-stale number forever.
CARRY_FORWARD_YEARS = 5


def load_mospi_income_series(csv_path: Path) -> pd.DataFrame:
    """Read the committed MoSPI PLFS snapshot and expand it into one row
    per (period=YYYY-MM, indicator, value, source) -- the shape
    affordability.calculate_affordability requires -- by holding each
    year's single real value flat across that year's 12 months, then
    carrying the latest real year's value forward for
    ``CARRY_FORWARD_YEARS`` more years (see module docstring).

    Returns an empty-but-correctly-shaped DataFrame if the file is
    missing, so a caller can treat "no income data" the same way
    affordability.py already does (STATUS_DATA_UNAVAILABLE), rather than
    raising.
    """
    columns = ["period", "indicator", "value", "source"]
    if not csv_path.exists():
        return pd.DataFrame(columns=columns)

    annual = pd.read_csv(csv_path)
    if annual.empty:
        return pd.DataFrame(columns=columns)

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

    latest_year = int(annual["year"].max())
    latest_value = float(annual.loc[annual["year"] == latest_year, "value"].iloc[0])
    for year in range(latest_year + 1, latest_year + 1 + CARRY_FORWARD_YEARS):
        for month in range(1, 13):
            rows.append(
                {
                    "period": f"{year:04d}-{month:02d}",
                    "indicator": INCOME_INDICATOR,
                    "value": latest_value,
                    "source": CARRIED_FORWARD_SOURCE_TAG,
                }
            )

    return pd.DataFrame(rows, columns=columns)


def default_mospi_income_path(repo_root: Path) -> Path:
    return repo_root / "data" / "benchmarks" / "mospi_plfs_income.csv"
