"""Data-access and preparation layer for the forecasting module.

STAGE 1 SCOPE. This module only builds a forecasting-ready HISTORICAL
dataset (national-level and route-level time series) from index_engine's
own public output. It deliberately does NOT:

  - recompute or duplicate any index/aggregation/cleaning/weighting logic
    (index_engine.index, .aggregation, .cleaning, .weighting remain the
    single source of truth for all of that);
  - fill, interpolate, forward-fill, or otherwise guess any missing value;
  - build any trend model, forecasting model, anomaly detector, or alert.

It calls exactly one public entry point, once per requested period:
``index_engine.AirfareAnalytics.calculate()`` — the same call
``examples/analytics_demo.py`` and ``examples/analytics_visuals.py``
already use. Every number in the resulting DataFrames was produced by
index_engine itself; this module only reshapes per-period results into a
multi-period table.
"""

from __future__ import annotations

import warnings as _warnings
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

import pandas as pd

from index_engine import AirfareAnalytics, IndexConfig
from index_engine.quality import STATUS_OK
from index_engine.volatility import VolatilityConfig

#: YYYY-MM, matching index_engine.normalization.add_period's period format.
PERIOD_FORMAT = "%Y-%m"

#: Default sanity bounds for derive_calendar_periods(), applied to RAW,
#: unvalidated flight_date values (this runs before index_engine's own
#: validation ever sees them). Catches obviously malformed/typo'd dates
#: (e.g. a stray "2099" or "1900") before they can expand the derived
#: period range to an unreasonable size. Configurable per call — these are
#: not hard-coded assumptions about any specific dataset.
DEFAULT_MAX_PAST_YEARS = 10
DEFAULT_MAX_FUTURE_DAYS = 400

#: Column order for the national-level table. Every value here traces back
#: to a field on index_engine.models.IndexResult or
#: index_engine.volatility.VolatilityResult — see build_forecasting_dataset.
NATIONAL_COLUMNS: List[str] = [
    "period",
    "national_index",
    "mom_change_pct",
    "yoy_change_pct",
    "routes_covered",
    "routes_total",
    "coverage_rate",
    "observations_used",
    "observations_received",
    "observations_rejected",
    "outliers_flagged",
    "representative_method",
    "aggregation_method",
    "national_volatility",
    "national_volatility_classification",
    "quality_flags",
]

#: Column order for the route-level panel. Every value here traces back to
#: a field on index_engine.route_analysis.RouteInflationRow (plus
#: observations_used, merged in from IndexResult.route_indices).
ROUTE_COLUMNS: List[str] = [
    "period",
    "route",
    "origin",
    "destination",
    "status",
    "route_index",
    "mom_inflation_pct",
    "yoy_inflation_pct",
    "weight_normalized",
    "traffic_weight",
    "contribution",
    "volatility",
    "observations_used",
]


def _derive_calendar_periods_detailed(
    observations: Union[pd.DataFrame, Sequence[dict]],
    date_column: str = "flight_date",
    reference_date: Optional[Union[str, pd.Timestamp]] = None,
    max_past_years: float = DEFAULT_MAX_PAST_YEARS,
    max_future_days: int = DEFAULT_MAX_FUTURE_DAYS,
) -> Tuple[List[str], int, int]:
    """Internal helper shared by ``derive_calendar_periods`` (which keeps
    its existing simple ``List[str]`` return type for backward
    compatibility) and ``build_forecasting_dataset`` (which wants the
    exclusion counts to record in ``ForecastingDataset.warnings``).

    Returns ``(periods, unparseable_count, out_of_range_count)``.
    """
    df = observations if isinstance(observations, pd.DataFrame) else pd.DataFrame(list(observations))
    if date_column not in df.columns or df.empty:
        return [], 0, 0

    reference_date = pd.Timestamp(reference_date) if reference_date is not None else pd.Timestamp.now()
    lower_bound = reference_date - pd.DateOffset(years=max_past_years)
    upper_bound = reference_date + pd.Timedelta(days=max_future_days)

    parsed = pd.to_datetime(df[date_column], errors="coerce")
    unparseable_count = int(parsed.isna().sum())

    valid = parsed.dropna()
    in_range_mask = (valid >= lower_bound) & (valid <= upper_bound)
    out_of_range_count = int((~in_range_mask).sum())

    usable = valid[in_range_mask]
    if usable.empty:
        return [], unparseable_count, out_of_range_count

    start = usable.min().to_period("M")
    end = usable.max().to_period("M")
    periods = [p.strftime(PERIOD_FORMAT) for p in pd.period_range(start, end, freq="M")]
    return periods, unparseable_count, out_of_range_count


def derive_calendar_periods(
    observations: Union[pd.DataFrame, Sequence[dict]],
    date_column: str = "flight_date",
    reference_date: Optional[Union[str, pd.Timestamp]] = None,
    max_past_years: float = DEFAULT_MAX_PAST_YEARS,
    max_future_days: int = DEFAULT_MAX_FUTURE_DAYS,
) -> List[str]:
    """Every ``YYYY-MM`` period from the earliest to the latest sane
    ``date_column`` value in ``observations``, inclusive, with no gaps.

    Uses ``flight_date`` by default, matching
    ``index_engine.normalization.add_period`` — the engine periods an
    observation by *when the flight is*, not when it was booked (see
    ``normalization.py``'s docstring). Using a different date_column would
    silently disagree with how the engine itself assigns periods.

    Deliberately does NOT skip a month just because it happens to have
    zero rows in ``observations``: a real scraping gap should surface
    downstream as an explicit DISCONTINUED / NO_BASE_DATA status on every
    route for that period (index_engine's own classification), not vanish
    because this function never asked the engine about that month.

    Date sanity bounds
    -------------------
    This function runs on RAW, unvalidated observations — before
    ``index_engine.validation`` ever sees them. A single malformed or
    typo'd real-world scraped date (e.g. a stray "2099" or "1900") would
    otherwise silently expand the derived period range to an unreasonable
    size, each spurious period then triggering a full, expensive
    ``AirfareAnalytics.calculate()`` call downstream. Any ``date_column``
    value more than ``max_past_years`` years before, or more than
    ``max_future_days`` days after, ``reference_date`` is excluded before
    the range is computed.

    ``reference_date`` defaults to "now" if not supplied, but should
    always be passed explicitly in tests (never rely on the implicit
    current date in a test assertion — it will silently go stale).

    If any values are excluded (unparseable or out of range), a
    ``UserWarning`` is raised via the standard ``warnings`` module —
    exclusions are never silent. ``build_forecasting_dataset`` additionally
    records this in ``ForecastingDataset.warnings`` when periods are
    auto-derived (see that function).
    """
    periods, unparseable_count, out_of_range_count = _derive_calendar_periods_detailed(
        observations, date_column, reference_date, max_past_years, max_future_days
    )
    if unparseable_count or out_of_range_count:
        _warnings.warn(
            f"derive_calendar_periods: excluded {unparseable_count} unparseable and "
            f"{out_of_range_count} out-of-sanity-bound {date_column!r} value(s) "
            f"(bounds: {max_past_years} year(s) past to {max_future_days} day(s) future of the reference date) "
            "before deriving the period range.",
            stacklevel=2,
        )
    return periods


def _validate_and_normalize_periods(periods: Sequence[str]) -> List[str]:
    """Validate a caller-supplied ``periods`` list before it drives any
    ``AirfareAnalytics.calculate()`` calls.

    Design choice (documented per Stage 3.1 audit item #4): malformed and
    duplicate period strings are REJECTED outright — both are genuinely
    ambiguous inputs that cannot be safely auto-corrected. Out-of-order
    input is NOT rejected; it is silently sorted ascending instead, since
    ordering is not load-bearing anywhere else in this module — every
    other view onto a ``ForecastingDataset`` (``national_series()``,
    ``route_series()``) already re-sorts by period rather than trusting
    input order, so rejecting an unsorted-but-otherwise-valid list would
    be inconsistent with the rest of the module's conventions for no
    real benefit.
    """
    malformed = [p for p in periods if not _is_valid_period_string(p)]
    if malformed:
        raise ValueError(f"Malformed period string(s), expected 'YYYY-MM': {malformed}")

    seen = set()
    duplicates = sorted({p for p in periods if (p in seen or seen.add(p))})
    if duplicates:
        raise ValueError(f"Duplicate period(s) supplied: {duplicates}")

    return sorted(periods, key=lambda p: pd.Period(p, freq="M"))


def _is_valid_period_string(period: str) -> bool:
    try:
        pd.Period(period, freq="M")
    except Exception:
        return False
    return True


@dataclass
class ForecastingDataset:
    """Forecasting-ready historical data: national-level and route-level
    panels, plus provenance so a caller never mistakes this for something
    computed independently of index_engine.

    ``national``: one row per requested period. ``national_index`` may be
    ``None`` for a period the engine could not compute a number for — that
    is a real signal (check ``quality_flags`` for that row), never an
    omitted row.

    ``routes``: one row per (route, period) for every route in
    index_engine's route universe, for every requested period. A route
    that has no usable data in a given period still gets a row — with
    ``status`` set to whatever index_engine classified it as
    (NEW_ROUTE / DISCONTINUED / INSUFFICIENT_DATA / NO_BASE_DATA) and
    ``route_index`` left as ``None``. Nothing is filled or dropped by
    default; use ``routes_ok()`` or ``route_series(..., ok_only=True)`` to
    opt into a status == OK-only view.
    """

    base_period: str
    periods: List[str]
    national: pd.DataFrame
    routes: pd.DataFrame
    warnings: List[str] = field(default_factory=list)

    def route_series(self, route: str, ok_only: bool = False) -> pd.DataFrame:
        """One route's time series (e.g. ``"BLR-DEL"``), sorted by period."""
        sub = self.routes[self.routes["route"] == route].sort_values("period").reset_index(drop=True)
        if ok_only:
            sub = sub[sub["status"] == STATUS_OK].reset_index(drop=True)
        return sub

    def national_series(self, ok_only: bool = False) -> pd.DataFrame:
        """The national-level series, sorted by period."""
        sub = self.national.sort_values("period").reset_index(drop=True)
        if ok_only:
            sub = sub[sub["national_index"].notna()].reset_index(drop=True)
        return sub

    def routes_ok(self) -> pd.DataFrame:
        """All route/period rows with ``status == OK`` — i.e. rows with a
        real, usable ``route_index``. An explicit opt-in filter: the base
        ``.routes`` table always keeps every status by default."""
        return self.routes[self.routes["status"] == STATUS_OK].reset_index(drop=True)

    def route_list(self) -> List[str]:
        """Every route present anywhere in the panel, sorted."""
        return sorted(self.routes["route"].unique())

    def to_dict(self) -> dict:
        return {
            "base_period": self.base_period,
            "periods": self.periods,
            "national": self.national.to_dict(orient="records"),
            "routes": self.routes.to_dict(orient="records"),
            "warnings": self.warnings,
        }


def build_forecasting_dataset(
    observations: Union[pd.DataFrame, Sequence[dict]],
    base_period: str,
    periods: Optional[List[str]] = None,
    weights: Optional[pd.DataFrame] = None,
    config: Optional[IndexConfig] = None,
    volatility_config: Optional[VolatilityConfig] = None,
    traffic_weight_coverage: Optional[float] = None,
) -> ForecastingDataset:
    """Build the historical national + route-level dataset later
    forecasting stages will train and backtest on.

    Calls ``index_engine.AirfareAnalytics.calculate()`` once per period —
    exactly the pattern already used in
    ``examples/analytics_demo.py`` / ``examples/analytics_visuals.py`` —
    and reshapes the results into two tidy DataFrames. No index,
    cleaning, aggregation, or weighting math happens in this function.

    Parameters
    ----------
    observations:
        Raw fare observations, same schema ``AirfarePriceIndex`` already
        requires (``index_engine.config.REQUIRED_COLUMNS``).
    base_period:
        Passed straight through to ``AirfareAnalytics`` — the period
        pinned to index value 100.
    periods:
        Periods to build history for. If omitted, derived from
        ``observations`` via :func:`derive_calendar_periods` (gap-free,
        keyed by ``flight_date``, with the same date-sanity bounds — see
        that function). If supplied explicitly, validated by
        :func:`_validate_and_normalize_periods`: malformed or duplicate
        period strings raise ``ValueError``; out-of-order input is sorted
        ascending, not rejected (see that function's docstring for why).
    weights, config, volatility_config, traffic_weight_coverage:
        Passed straight through to ``AirfareAnalytics`` unchanged — this
        function does not set defaults or reinterpret any of these; if
        omitted, whatever ``AirfareAnalytics``/``AirfarePriceIndex``
        themselves default to (e.g. synthetic weights) applies.

    Raises
    ------
    ValueError
        If ``periods`` is empty and none could be derived from
        ``observations`` (e.g. no parseable ``flight_date`` values).
    index_engine.exceptions.InsufficientDataError
        Propagated, not caught: raised by the engine if zero observations
        survive validation/cleaning across the entire input — a real
        "there is nothing to build a dataset from" condition, not
        something this layer should hide or paper over.
    """
    df = observations if isinstance(observations, pd.DataFrame) else pd.DataFrame(list(observations))

    warnings: List[str] = []
    if periods is not None:
        periods = _validate_and_normalize_periods(list(periods))
    else:
        periods, unparseable_count, out_of_range_count = _derive_calendar_periods_detailed(df)
        if unparseable_count or out_of_range_count:
            warnings.append(
                f"Period derivation excluded {unparseable_count} unparseable and "
                f"{out_of_range_count} out-of-sanity-bound flight_date value(s) before deriving the "
                "period range; see derive_calendar_periods()'s reference_date/max_past_years/max_future_days "
                "parameters to adjust the bounds."
            )

    if not periods:
        raise ValueError(
            "No periods to build: pass `periods` explicitly, or ensure `observations` "
            "has parseable, in-range `flight_date` values so periods can be derived."
        )

    analytics = AirfareAnalytics(
        base_period=base_period,
        weights=weights,
        config=config,
        volatility_config=volatility_config,
        traffic_weight_coverage=traffic_weight_coverage,
    )

    national_rows = []
    route_rows = []

    for period in periods:
        result = analytics.calculate(df, current_period=period)
        idx = result.price_index
        vol = result.volatility

        national_rows.append(
            {
                "period": period,
                "national_index": idx.national_index,
                "mom_change_pct": idx.mom_change_pct,
                "yoy_change_pct": idx.yoy_change_pct,
                "routes_covered": idx.routes_covered,
                "routes_total": idx.routes_total,
                "coverage_rate": idx.coverage_rate,
                "observations_used": idx.observations_used,
                "observations_received": idx.observations_received,
                "observations_rejected": idx.observations_rejected,
                "outliers_flagged": idx.outliers_flagged,
                "representative_method": idx.representative_method,
                "aggregation_method": idx.aggregation_method,
                "national_volatility": vol.national_volatility,
                "national_volatility_classification": vol.national_classification,
                "quality_flags": "; ".join(idx.quality_flags) if idx.quality_flags else None,
            }
        )
        if idx.national_index is None:
            warnings.append(f"{period}: national_index is None (see that row's quality_flags)")

        observations_used_by_route = {r.route: r.observations_used for r in idx.route_indices}
        for row in result.route_inflation:
            route_rows.append(
                {
                    "period": period,
                    "route": row.route,
                    "origin": row.origin,
                    "destination": row.destination,
                    "status": row.status,
                    "route_index": row.current_index,
                    "mom_inflation_pct": row.mom_inflation_pct,
                    "yoy_inflation_pct": row.yoy_inflation_pct,
                    "weight_normalized": row.weight,
                    "traffic_weight": row.traffic_weight,
                    "contribution": row.contribution,
                    "volatility": row.volatility,
                    "observations_used": observations_used_by_route.get(row.route, 0),
                }
            )

    national_df = pd.DataFrame(national_rows, columns=NATIONAL_COLUMNS)
    routes_df = pd.DataFrame(route_rows, columns=ROUTE_COLUMNS)

    return ForecastingDataset(
        base_period=base_period,
        periods=periods,
        national=national_df,
        routes=routes_df,
        warnings=warnings,
    )
