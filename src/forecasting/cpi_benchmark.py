"""CPI benchmark/comparison layer: our national index vs. MoSPI's official
CPI Airfare sub-index.

Compares the two series in REBASED, GROWTH-RATE form — never raw levels.
The two indices sit on different bases (our ``base_period`` vs. MoSPI's
``base_year``) and reflect fundamentally different methodologies (DGCA
traffic-weighted median-of-scraped-fares across ~10 routes vs. MoSPI's
official, nationally representative, expenditure-weighted collection).
Comparing raw levels would be meaningless; comparing rebased trajectories
and period-over-period growth is the statistically defensible approach.

IMPORTANT — this module is a structural comparison PIPELINE, not a
validation exercise. With the project's current SYNTHETIC fare data
(``generate_sample_fares.py``, ``random.seed(42)``), every metric this
module produces describes how a FABRICATED series happens to move
relative to MoSPI's real CPI — never evidence of real-world tracking
accuracy, in either direction. Every result carries
``is_synthetic_airfare_data`` explicitly for exactly this reason, and
`notes` on every OK result restates this. A future difference from MoSPI
on real data would also not automatically indicate an error in either
series, given the methodological differences above — that must be stated
alongside any reported number, not left implicit.

Does not touch index_engine or data_quality: reads only already-computed
values via ``forecasting.series.national_index_series`` and MoSPI's own
extract via ``forecasting.cpi_loader``.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pandas as pd
from index_engine.utils import shift_period

from forecasting.cpi_loader import MospiCpiSeries
from forecasting.cpi_results import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_INSUFFICIENT_OVERLAP,
    STATUS_OK,
    CPIBenchmarkResult,
    CPIPeriodComparison,
)
from forecasting.data_access import ForecastingDataset
from forecasting.series import national_index_series

#: Minimum MoM-difference pairs before a mean absolute difference is
#: reported (>=2 pairs implies >=3 consecutive, calendar-adjacent
#: overlapping levels).
MIN_PAIRS_FOR_MEAN_ABS_DIFF = 2

#: Minimum MoM-difference pairs before a correlation is reported at all.
#: Even at this minimum, the result is explicitly labeled illustrative —
#: see the notes construction below.
MIN_PAIRS_FOR_CORRELATION = 4


def _rebase(series: pd.Series, base_period: str) -> pd.Series:
    """Rebase ``series`` to 100 at ``base_period``. Returns an empty
    Series (not a fabricated fallback) if the base value is missing,
    NaN, or zero."""
    base_value = series.get(base_period)
    if base_value is None or pd.isna(base_value) or base_value == 0:
        return pd.Series(dtype=float)
    return 100.0 * series / base_value


def _pearson_correlation(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    if n < 2:
        return None
    mean_x, mean_y = sum(x) / n, sum(y) / n
    covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    variance_x = sum((xi - mean_x) ** 2 for xi in x)
    variance_y = sum((yi - mean_y) ** 2 for yi in y)
    if variance_x == 0 or variance_y == 0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def _find_overlap_periods(our_series: pd.Series, mospi_series: pd.Series) -> List[str]:
    """Periods present, and non-missing, on BOTH sides. Never filled or
    guessed — a period missing on either side is simply excluded."""
    shared = set(our_series.index) & set(mospi_series.index)
    overlap = [
        p for p in shared
        if pd.notna(our_series.get(p)) and pd.notna(mospi_series.get(p))
    ]
    return sorted(overlap)


#: Minimum YoY-difference pairs before a mean absolute YoY difference is
#: reported — mirrors ``MIN_PAIRS_FOR_MEAN_ABS_DIFF`` for MoM.
MIN_PAIRS_FOR_MEAN_ABS_YOY_DIFF = 2


def _compute_yoy_pairs(
    overlap_periods: List[str],
    by_period: dict,
) -> List[Tuple[float, float]]:
    """Populate ``our_yoy_pct``/``mospi_yoy_pct``/``yoy_difference_pct_points``
    on each :class:`CPIPeriodComparison` in ``by_period`` (mutated in
    place, mirroring how the MoM loop mutates ``comparisons``) and return
    the list of ``(our_yoy, mospi_yoy)`` pairs actually computed.

    A period gets a YoY value ONLY when the period exactly 12 months
    prior is ALSO in the our/MoSPI overlap (i.e. present in
    ``by_period``) and both periods are ``included_in_metrics``. No
    12-months-prior observation on either side -> that period is simply
    excluded from YoY, never fabricated or interpolated. This also means
    a period whose prior value exists on only one side (a "mismatched"
    period — e.g. our series has month P-12 but MoSPI's overlap doesn't,
    because MoSPI was missing or imputed-and-excluded there) correctly
    gets no YoY value, since ``by_period`` only contains periods present
    on BOTH sides to begin with.
    """
    yoy_pairs: List[Tuple[float, float]] = []
    for period in overlap_periods:
        prior_period = shift_period(period, -12)
        prior_c = by_period.get(prior_period)
        if prior_c is None:
            continue  # no 12-months-prior observation in the overlap — never fabricate one

        curr_c = by_period[period]
        if not (curr_c.included_in_metrics and prior_c.included_in_metrics):
            continue
        if prior_c.our_index_rebased in (None, 0) or prior_c.mospi_index_rebased in (None, 0):
            continue

        our_yoy = 100.0 * (curr_c.our_index_rebased / prior_c.our_index_rebased - 1.0)
        mospi_yoy = 100.0 * (curr_c.mospi_index_rebased / prior_c.mospi_index_rebased - 1.0)
        curr_c.our_yoy_pct = our_yoy
        curr_c.mospi_yoy_pct = mospi_yoy
        curr_c.yoy_difference_pct_points = our_yoy - mospi_yoy
        yoy_pairs.append((our_yoy, mospi_yoy))

    return yoy_pairs


def compare_to_mospi_cpi(
    dataset: ForecastingDataset,
    mospi: MospiCpiSeries,
    is_synthetic_airfare_data: bool,
    min_coverage_rate: Optional[float] = None,
    exclude_mospi_imputed: bool = True,
) -> CPIBenchmarkResult:
    """Compare our national index against MoSPI's official CPI Airfare
    sub-index over whatever periods both series have a trustworthy value
    for.

    Parameters
    ----------
    dataset:
        A ``ForecastingDataset`` (see ``forecasting.data_access``).
    mospi:
        A parsed ``MospiCpiSeries`` (see ``forecasting.cpi_loader``).
    is_synthetic_airfare_data:
        REQUIRED, no default — the caller must state explicitly whether
        ``dataset`` was built from synthetic or real fare data. This is
        never silently assumed either way; see module docstring for why
        it matters.
    min_coverage_rate:
        Passed straight through to
        ``forecasting.series.national_index_series`` — see that
        function's docstring. ``None`` applies no additional filtering.
    exclude_mospi_imputed:
        If ``True`` (default), a period where MoSPI's own ``imputation``
        flag is set is excluded from MoM/correlation metrics (its
        rebased level is still reported, for transparency) — an imputed
        MoSPI value is not an original observation, and this project has
        no basis to treat it as equally trustworthy as one that is.

    Returns
    -------
    CPIBenchmarkResult with ``status = INSUFFICIENT_OVERLAP`` and no
    comparisons if no period is trustworthy on both sides — never a
    fabricated or interpolated comparison.
    """
    our_series = national_index_series(dataset, min_coverage_rate=min_coverage_rate)
    mospi_series = mospi.index_series()

    overlap_periods = _find_overlap_periods(our_series, mospi_series)

    if not overlap_periods:
        return CPIBenchmarkResult(
            overlap_start=None,
            overlap_end=None,
            overlap_period_count=0,
            rebase_period=None,
            comparisons=[],
            mean_absolute_mom_difference_pct_points=None,
            mom_correlation=None,
            mom_correlation_status=STATUS_INSUFFICIENT_OVERLAP,
            yoy_comparison_status=STATUS_INSUFFICIENT_OVERLAP,
            mean_absolute_yoy_difference_pct_points=None,
            yoy_period_count=0,
            mospi_base_year=mospi.base_year,
            mospi_source_file=mospi.source_file,
            status=STATUS_INSUFFICIENT_OVERLAP,
            is_synthetic_airfare_data=is_synthetic_airfare_data,
            notes="No period has a trustworthy value on both our side and MoSPI's side — nothing to compare.",
        )

    rebase_period = overlap_periods[0]
    our_rebased = _rebase(our_series, rebase_period)
    mospi_rebased = _rebase(mospi_series, rebase_period)

    comparisons: List[CPIPeriodComparison] = []
    for period in overlap_periods:
        imputed = mospi.imputed_by_period.get(period, False)
        included = True
        exclusion_reason = None
        if exclude_mospi_imputed and imputed:
            included = False
            exclusion_reason = "MoSPI value for this period is flagged as imputed."

        comparisons.append(
            CPIPeriodComparison(
                period=period,
                our_index_rebased=float(our_rebased[period]) if period in our_rebased.index else None,
                mospi_index_rebased=float(mospi_rebased[period]) if period in mospi_rebased.index else None,
                our_mom_pct=None,
                mospi_mom_pct=None,
                mom_difference_pct_points=None,
                our_yoy_pct=None,
                mospi_yoy_pct=None,
                yoy_difference_pct_points=None,
                mospi_imputed=imputed,
                included_in_metrics=included,
                exclusion_reason=exclusion_reason,
            )
        )

    by_period = {c.period: c for c in comparisons}
    mom_pairs: List[Tuple[float, float]] = []

    for i in range(1, len(overlap_periods)):
        prev_period, curr_period = overlap_periods[i - 1], overlap_periods[i]
        if shift_period(prev_period, 1) != curr_period:
            continue  # not calendar-adjacent within the overlap — never bridge a gap

        prev_c, curr_c = by_period[prev_period], by_period[curr_period]
        if not (prev_c.included_in_metrics and curr_c.included_in_metrics):
            continue
        if prev_c.our_index_rebased in (None, 0) or prev_c.mospi_index_rebased in (None, 0):
            continue

        our_mom = 100.0 * (curr_c.our_index_rebased / prev_c.our_index_rebased - 1.0)
        mospi_mom = 100.0 * (curr_c.mospi_index_rebased / prev_c.mospi_index_rebased - 1.0)
        curr_c.our_mom_pct = our_mom
        curr_c.mospi_mom_pct = mospi_mom
        curr_c.mom_difference_pct_points = our_mom - mospi_mom
        mom_pairs.append((our_mom, mospi_mom))

    if len(mom_pairs) >= MIN_PAIRS_FOR_MEAN_ABS_DIFF:
        mean_abs_diff = sum(abs(o - m) for o, m in mom_pairs) / len(mom_pairs)
    else:
        mean_abs_diff = None

    yoy_pairs = _compute_yoy_pairs(overlap_periods, by_period)
    if yoy_pairs:
        yoy_comparison_status = STATUS_OK
    else:
        yoy_comparison_status = STATUS_INSUFFICIENT_DATA
    if len(yoy_pairs) >= MIN_PAIRS_FOR_MEAN_ABS_YOY_DIFF:
        mean_abs_yoy_diff = sum(abs(o - m) for o, m in yoy_pairs) / len(yoy_pairs)
    else:
        mean_abs_yoy_diff = None

    if len(mom_pairs) >= MIN_PAIRS_FOR_CORRELATION:
        correlation = _pearson_correlation([o for o, _ in mom_pairs], [m for _, m in mom_pairs])
        correlation_status = STATUS_OK if correlation is not None else STATUS_INSUFFICIENT_DATA
    else:
        correlation = None
        correlation_status = STATUS_INSUFFICIENT_DATA

    notes_parts = []
    if is_synthetic_airfare_data:
        notes_parts.append(
            "Airfare data is SYNTHETIC: these metrics describe how a fabricated series happens to move "
            "relative to MoSPI's real CPI, not evidence of real-world tracking accuracy."
        )
    if correlation is not None:
        notes_parts.append(
            f"Correlation computed from only {len(mom_pairs)} MoM pair(s) — illustrative only, not a "
            "statistically reliable measure of relationship."
        )
    if yoy_pairs and len(yoy_pairs) < MIN_PAIRS_FOR_MEAN_ABS_YOY_DIFF:
        notes_parts.append(
            f"YoY comparison computed from only {len(yoy_pairs)} aligned 12-months-apart period(s) — "
            "a single data point, not a trend."
        )
    notes_parts.append(
        "Our national index and MoSPI's CPI use different base periods, weighting methodologies, and "
        "sampling coverage — a difference between them is not automatically an error in either series."
    )

    return CPIBenchmarkResult(
        overlap_start=overlap_periods[0],
        overlap_end=overlap_periods[-1],
        overlap_period_count=len(overlap_periods),
        rebase_period=rebase_period,
        comparisons=comparisons,
        mean_absolute_mom_difference_pct_points=mean_abs_diff,
        mom_correlation=correlation,
        mom_correlation_status=correlation_status,
        yoy_comparison_status=yoy_comparison_status,
        mean_absolute_yoy_difference_pct_points=mean_abs_yoy_diff,
        yoy_period_count=len(yoy_pairs),
        mospi_base_year=mospi.base_year,
        mospi_source_file=mospi.source_file,
        status=STATUS_OK,
        is_synthetic_airfare_data=is_synthetic_airfare_data,
        notes=" ".join(notes_parts),
    )
