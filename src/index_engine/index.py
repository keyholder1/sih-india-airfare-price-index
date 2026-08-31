"""Public entry point: :class:`AirfarePriceIndex`.

Pipeline (see docs/methodology.md for the full rationale of each step):

    raw observations
        -> validation            (structural checks, reasons recorded)
        -> normalization         (route, period, booking horizon, standardized fare)
        -> booking-horizon filter (optional)
        -> cleaning               (duplicates, outliers, reasons recorded)
        -> representative fare per (route, period)
        -> route price relative -> route index (vs. base period)
        -> weighted national index
        -> MoM / YoY (national index compared across periods)
        -> route contribution to MoM change
        -> quality flags + coverage rate
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Union

import pandas as pd

from . import aggregation, cleaning, contribution, normalization, quality, validation, weighting
from .config import IndexConfig
from .exceptions import InsufficientDataError
from .models import CleaningReport, IndexResult, RouteIndexResult
from .utils import pct_change, shift_period

ENRICHED_COLUMNS = ("route", "period", "booking_horizon_days", "booking_horizon_bucket", "standardized_fare")


class AirfarePriceIndex:
    """Computes a national airfare price index from fare observations.

    Parameters
    ----------
    base_period:
        ``YYYY-MM`` period pinned to index value 100.
    weights:
        Optional route weights DataFrame with columns
        ``origin, destination, weight[, effective_from, effective_to, source]``.
        If omitted, clearly-labelled synthetic weights are generated from
        whatever routes are present in the observations passed to
        :meth:`calculate` — see :func:`index_engine.weighting.generate_synthetic_weights`.
    config:
        Optional :class:`IndexConfig`. If omitted, sensible defaults are
        used with ``base_period`` set as above.
    """

    def __init__(
        self,
        base_period: str,
        weights: Optional[pd.DataFrame] = None,
        config: Optional[IndexConfig] = None,
    ) -> None:
        self.base_period = base_period
        self.config = config or IndexConfig(base_period=base_period)
        if self.config.base_period != base_period:
            raise ValueError("base_period argument must match config.base_period")
        self._weights = weights

    def calculate(self, observations: Union[pd.DataFrame, Sequence[dict]], current_period: str) -> IndexResult:
        """Compute the index for ``current_period`` relative to the base period.

        Raises
        ------
        InsufficientDataError
            If zero observations survive validation and cleaning — there is
            nothing to compute an index from at all. Per-route gaps (a
            single route missing data) do NOT raise; they show up as a
            ``status`` other than ``OK`` on that route's result instead.
        """
        df = self._to_dataframe(observations)
        total_input = len(df)

        valid, rejected = validation.validate_observations(df)
        enriched = self._enrich_or_empty(valid)

        clean, partial_report = cleaning.clean_observations(enriched, self.config, total_input=len(valid))
        cleaning_report = self._merge_cleaning_report(total_input, clean, partial_report, rejected)

        if len(clean) == 0:
            raise InsufficientDataError(
                "No valid observations survived validation and cleaning; cannot compute an index. "
                f"Cleaning report: {cleaning_report.to_dict()}"
            )

        route_period_fares = aggregation.compute_route_period_fares(clean, self.config)
        observed_routes = set(route_period_fares["route"].unique())

        weights_raw = self._weights if self._weights is not None else weighting.generate_synthetic_weights(sorted(observed_routes))
        weights_for_current = weighting.weights_for_period(weights_raw, current_period)
        weighted_routes = set(weights_for_current["route"].unique()) if len(weights_for_current) else set()
        weights_for_current = weighting.normalize_weights(weights_for_current)

        all_routes = sorted(observed_routes | weighted_routes)

        prev_month = shift_period(current_period, -1)
        prev_year = shift_period(current_period, -12)

        current_results = self._route_indices(route_period_fares, weights_for_current, current_period, all_routes)
        prev_month_results = self._route_indices(route_period_fares, weights_for_current, prev_month, all_routes)
        prev_year_results = self._route_indices(route_period_fares, weights_for_current, prev_year, all_routes)

        national_current = aggregation.national_index(current_results, self.config.aggregation_method)
        national_prev_month = aggregation.national_index(prev_month_results, self.config.aggregation_method)
        national_prev_year = aggregation.national_index(prev_year_results, self.config.aggregation_method)

        mom = (
            pct_change(national_current, national_prev_month)
            if national_current is not None and national_prev_month
            else None
        )
        yoy = (
            pct_change(national_current, national_prev_year)
            if national_current is not None and national_prev_year
            else None
        )

        contributions = contribution.compute_contributions(current_results, prev_month_results, self.config.aggregation_method)
        flags = quality.compute_quality_flags(current_results, cleaning_report.total_removed, total_input)
        coverage = quality.coverage_rate(current_results)
        routes_covered = sum(1 for r in current_results if r.status == quality.STATUS_OK)

        # National index at each period is a weighted average over only the
        # routes OK *at that period* (aggregation.national_index renormalizes
        # over that period's usable subset). So if route composition changes
        # between two periods being compared, part of MoM/YoY reflects that
        # compositional shift, not pure price movement — and contribution
        # points only sum exactly to the point change when the *same* routes
        # are OK in both periods. Surface both explicitly rather than
        # silently implying an exact, composition-free comparison.
        ok_now = {r.route for r in current_results if r.status == quality.STATUS_OK}
        ok_prev_month = {r.route for r in prev_month_results if r.status == quality.STATUS_OK}
        ok_prev_year = {r.route for r in prev_year_results if r.status == quality.STATUS_OK}

        mismatched_mom = ok_now.symmetric_difference(ok_prev_month)
        if mismatched_mom:
            flags.append(
                f"{len(mismatched_mom)} route(s) changed OK/not-OK status between {prev_month} and {current_period} "
                f"({sorted(mismatched_mom)}); MoM reflects a partial change in route composition, and its "
                "contribution decomposition is partial for those routes."
            )

        mismatched_yoy = ok_now.symmetric_difference(ok_prev_year)
        if mismatched_yoy:
            flags.append(
                f"{len(mismatched_yoy)} route(s) changed OK/not-OK status between {prev_year} and {current_period} "
                f"({sorted(mismatched_yoy)}); YoY reflects a partial change in route composition, not pure price movement, for those routes."
            )

        obs_used_series = route_period_fares.loc[route_period_fares["period"] == current_period, "observations_used"]
        outliers_flagged = sum(v for k, v in cleaning_report.removed_by_reason.items() if k.startswith("OUTLIER"))
        routes_with_data = sum(1 for r in current_results if r.status != quality.STATUS_NO_BASE_DATA)

        return IndexResult(
            base_period=self.base_period,
            current_period=current_period,
            national_index=national_current,
            mom_change_pct=mom,
            yoy_change_pct=yoy,
            routes_covered=routes_covered,
            routes_total=len(current_results),
            observations_used=int(obs_used_series.sum()),
            coverage_rate=coverage,
            representative_method=self.config.representative_method,
            aggregation_method=self.config.aggregation_method,
            route_indices=current_results,
            route_contributions=contributions,
            quality_flags=flags,
            cleaning_report=cleaning_report,
            observations_received=cleaning_report.total_input,
            observations_rejected=cleaning_report.total_removed,
            outliers_flagged=outliers_flagged,
            routes_expected=len(current_results),
            routes_with_data=routes_with_data,
        )

    def _enrich_or_empty(self, valid: pd.DataFrame) -> pd.DataFrame:
        if len(valid) == 0:
            enriched = valid.copy()
            for col in ENRICHED_COLUMNS:
                enriched[col] = pd.Series(dtype="object")
            return enriched
        enriched = normalization.enrich(valid, self.config)
        if self.config.booking_horizon_filter:
            enriched = enriched[enriched["booking_horizon_bucket"] == self.config.booking_horizon_filter]
        return enriched

    @staticmethod
    def _merge_cleaning_report(
        total_input: int,
        clean: pd.DataFrame,
        partial_report: CleaningReport,
        rejected: pd.DataFrame,
    ) -> CleaningReport:
        removed_by_reason = dict(partial_report.removed_by_reason)
        if len(rejected):
            for reason, count in rejected["rejection_reason"].value_counts().items():
                removed_by_reason[reason] = removed_by_reason.get(reason, 0) + int(count)
        return CleaningReport(
            total_input=total_input,
            total_valid=len(clean),
            total_removed=total_input - len(clean),
            removed_by_reason=removed_by_reason,
        )

    def _route_indices(
        self,
        route_period_fares: pd.DataFrame,
        weights_df: pd.DataFrame,
        period: str,
        all_routes: List[str],
    ) -> List[RouteIndexResult]:
        by_route_period = {(row.route, row.period): row for row in route_period_fares.itertuples()}
        weight_by_route = {row.route: row for row in weights_df.itertuples()} if len(weights_df) else {}

        results = []
        for route in all_routes:
            origin, destination = route.split("-", 1)
            weight_row = weight_by_route.get(route)
            weight_raw = getattr(weight_row, "weight", None) if weight_row is not None else None
            weight_normalized = getattr(weight_row, "weight_normalized", None) if weight_row is not None else None

            base_row = by_route_period.get((route, self.base_period))
            period_row = by_route_period.get((route, period))

            status, route_index = self._classify(base_row, period_row)

            results.append(
                RouteIndexResult(
                    route=route,
                    origin=origin,
                    destination=destination,
                    period=period,
                    base_period_fare=base_row.representative_fare if base_row is not None else None,
                    period_fare=period_row.representative_fare if period_row is not None else None,
                    route_index=route_index,
                    observations_used=int(period_row.observations_used) if period_row is not None else 0,
                    weight_raw=weight_raw,
                    weight_normalized=weight_normalized,
                    status=status,
                )
            )
        return results

    @staticmethod
    def _classify(base_row, period_row):
        if base_row is None and period_row is None:
            return quality.STATUS_NO_BASE_DATA, None
        if base_row is None:
            return quality.STATUS_NEW_ROUTE, None
        if not base_row.sufficient_data or base_row.representative_fare in (None, 0):
            return quality.STATUS_INSUFFICIENT_DATA, None
        if period_row is None:
            return quality.STATUS_DISCONTINUED, None
        if not period_row.sufficient_data:
            return quality.STATUS_INSUFFICIENT_DATA, None
        route_index = 100.0 * period_row.representative_fare / base_row.representative_fare
        return quality.STATUS_OK, route_index

    @staticmethod
    def _to_dataframe(observations) -> pd.DataFrame:
        if isinstance(observations, pd.DataFrame):
            return observations.copy()
        return pd.DataFrame(list(observations))
