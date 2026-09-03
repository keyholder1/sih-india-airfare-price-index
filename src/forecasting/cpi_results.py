"""Result dataclasses for the CPI benchmark/comparison layer.

Mirrors the conventions already established in ``forecasting.results``:
plain dataclasses, ``.to_dict()`` for JSON-serializable output, explicit
``status`` fields, ``Optional`` for anything not legitimately computable,
and nothing fabricated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional

STATUS_OK = "OK"
#: No period exists where BOTH our series and MoSPI's series have a
#: trustworthy value — nothing to compare.
STATUS_INSUFFICIENT_OVERLAP = "INSUFFICIENT_OVERLAP"
#: A specific metric's minimum-data gate was not met — the metric itself
#: is None, this status explains why, without invalidating the rest of
#: the result.
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class CPIPeriodComparison:
    """One overlapping period's comparison between our (rebased) index
    and MoSPI's (rebased) index.

    ``our_mom_pct``/``mospi_mom_pct``/``mom_difference_pct_points`` are
    only populated when this period and the immediately preceding
    calendar period are both present, calendar-adjacent (no gap), and
    ``included_in_metrics`` — never computed across a gap or an excluded
    period.

    ``our_yoy_pct``/``mospi_yoy_pct``/``yoy_difference_pct_points`` are
    only populated when this period AND the period exactly 12 months
    prior are both present in the our/MoSPI overlap and
    ``included_in_metrics`` — never fabricated across a missing prior
    period, and never computed if the two series' overlaps don't line up
    12 months apart (a "mismatched" case: one side may individually have
    a 12-months-prior value, but if it isn't also in the overlap, no
    YoY comparison is made for this period).
    """

    period: str
    our_index_rebased: Optional[float]
    mospi_index_rebased: Optional[float]
    our_mom_pct: Optional[float]
    mospi_mom_pct: Optional[float]
    mom_difference_pct_points: Optional[float]
    our_yoy_pct: Optional[float]
    mospi_yoy_pct: Optional[float]
    yoy_difference_pct_points: Optional[float]
    mospi_imputed: bool
    included_in_metrics: bool
    exclusion_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CPIBenchmarkResult:
    """Full output of :func:`forecasting.cpi_benchmark.compare_to_mospi_cpi`.

    ``is_synthetic_airfare_data`` must be passed explicitly by the caller
    (see that function's signature) — never silently defaulted in a way
    that could mislabel real data as synthetic or vice versa.

    ``yoy_comparison_status`` is ``STATUS_INSUFFICIENT_OVERLAP`` when
    there is no overlapping period at all (mirrors ``status``),
    ``STATUS_INSUFFICIENT_DATA`` when overlap exists but no period has a
    valid 12-months-prior pair on both sides, and ``STATUS_OK`` once at
    least one such pair exists. ``yoy_period_count`` is the number of
    periods with a populated ``our_yoy_pct``/``mospi_yoy_pct`` pair;
    ``mean_absolute_yoy_difference_pct_points`` mirrors the MoM
    equivalent's minimum-pairs gate (``None`` below that gate).
    """

    overlap_start: Optional[str]
    overlap_end: Optional[str]
    overlap_period_count: int
    rebase_period: Optional[str]
    comparisons: List[CPIPeriodComparison]
    mean_absolute_mom_difference_pct_points: Optional[float]
    mom_correlation: Optional[float]
    mom_correlation_status: str
    yoy_comparison_status: str
    mean_absolute_yoy_difference_pct_points: Optional[float]
    yoy_period_count: int
    mospi_base_year: Optional[int]
    mospi_source_file: Optional[str]
    status: str
    is_synthetic_airfare_data: bool
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
