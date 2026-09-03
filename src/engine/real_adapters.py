"""Real implementations of the engine Protocols (src/engine/protocols.py),
wired against the actual index_engine / data_quality / news-context
modules instead of fabricated stub data.

Every class here is a thin adapter: it loads/maps data, calls the real
statistical/quality/news modules, and reshapes their output into the
Protocol dataclasses the API layer already knows how to serialize. No
statistics are computed in this file.

``data_source`` is always the honest signal these modules were already
built around: "real" only when the underlying observations are genuinely
scraped (not scraper mock output, not this file's own demo fallback),
"synthetic" otherwise. See data_access.py for how that's determined.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from index_engine import AirfarePriceIndex
from index_engine.mock_news_provider import MockNewsProvider
from index_engine.news_context import NewsContextService, route_movement_from_row
from index_engine.route_analysis import RouteInflationRow
from index_engine.utils import pct_change, shift_period
from index_engine import traffic as traffic_mod
from index_engine import weighting as weighting_mod

import data_quality as data_quality_mod

from src.engine import data_access
from src.engine.protocols import (
    IndexResult,
    NewsEvent,
    QualityReport,
    RouteAnalysis,
    RouteContext,
    RouteHealth,
    RouteIndex,
    SourceHealth,
    TimeseriesPoint,
)

REPO_ROOT = data_access.REPO_ROOT
DGCA_TRAFFIC_CSV = str(REPO_ROOT / "data" / "traffic" / "dgca_domestic_city_pairs.csv")

#: The mock news fixture data (mock_news_provider.DEMO_ARTICLES) is
#: anchored around 2026-08-14 (see that module's docstring). No real news
#: provider is wired in anywhere in this project yet, so every response
#: from this adapter is "synthetic" regardless of whether the underlying
#: fare data is real -- news context is a separate, still-mock layer.
_NEWS_DEMO_ANCHOR = datetime(2026, 8, 14, 9, 0, 0, tzinfo=timezone.utc)
_NEWS_DATA_SOURCE = "synthetic"


def _safe_pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return pct_change(current, previous)


def _period_bounds(observations: List[Dict[str, Any]]) -> tuple[str, str]:
    periods = data_access.available_periods(observations)
    if not periods:
        raise ValueError("No periods available in the loaded observation set.")
    return periods[0], periods[-1]


def _build_weights(observations: List[Dict[str, Any]]) -> tuple[pd.DataFrame, bool]:
    """Real DGCA-traffic-derived weights when every observed route maps to
    a known city (see city_mapping.IATA_TO_CITY); synthetic (equal-weight)
    otherwise. Never raises -- a mapping gap degrades to synthetic rather
    than breaking the endpoint."""
    routes = data_access.observed_routes(observations)
    if not routes:
        return pd.DataFrame(columns=["origin", "destination", "weight"]), False
    try:
        weights_df, _diagnostics = traffic_mod.build_dgca_weights(DGCA_TRAFFIC_CSV, routes)
        if len(weights_df) == 0:
            raise ValueError("DGCA weights produced no rows for the observed routes.")
        return weights_df, True
    except Exception:
        route_codes = [f"{o}-{d}" for o, d in routes]
        return weighting_mod.generate_synthetic_weights(route_codes), False


def _calculate(df: pd.DataFrame, weights: pd.DataFrame, base_period: str, current_period: str):
    engine = AirfarePriceIndex(base_period=base_period, weights=weights if len(weights) else None)
    return engine.calculate(observations=df, current_period=current_period)


class RealIndexEngine:
    """Real implementation of ``IndexEngineProtocol``."""

    def calculate_index(
        self,
        observations: List[Dict[str, Any]],
        base_period: str,
        current_period: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> IndexResult:
        # The API's simplified ObservationInput shape (route/fare/date/source)
        # -> the full data_contract.md shape AirfarePriceIndex expects.
        # airline/currency/booking_date aren't collected by this simplified
        # schema; UNKNOWN/INR/same-day-booking are documented placeholders,
        # not fabricated statistics -- the engine never uses `airline` for
        # grouping (see docs/data_contract.md), and booking_date only feeds
        # booking-horizon analytics this endpoint doesn't expose.
        mapped = []
        for i, obs in enumerate(observations):
            origin, destination = obs["route"].split("-")
            mapped.append(
                {
                    "observation_id": f"api-{i}-{obs['route']}-{obs['date']}",
                    "airline": "UNKNOWN",
                    "origin": origin,
                    "destination": destination,
                    "flight_date": obs["date"],
                    "booking_date": obs["date"],
                    "total_fare": obs["fare"],
                    "currency": "INR",
                }
            )
        df = pd.DataFrame(mapped)
        result = _calculate(df, pd.DataFrame(), base_period, current_period)

        # The caller labels each observation "real" or "synthetic" itself
        # (see ObservationInput.source's own description) -- this endpoint
        # always computes from exactly the data it was given, so it trusts
        # that label rather than re-deriving one.
        data_source = "real" if observations and all(o.get("source") == "real" for o in observations) else "synthetic"

        contribution_by_route = {c.route: c.contribution_points for c in result.route_contributions}
        route_indices = [
            RouteIndex(
                route=ri.route,
                index=ri.route_index if ri.route_index is not None else 0.0,
                mom=None,  # not computed for this single-shot call; see get_timeseries for MoM
                weight=ri.weight_normalized or 0.0,
                contribution=contribution_by_route.get(ri.route) or 0.0,
                data_source=data_source,
            )
            for ri in result.route_indices
        ]

        return IndexResult(
            national_index=result.national_index if result.national_index is not None else 100.0,
            mom=result.mom_change_pct,
            yoy=result.yoy_change_pct,
            base_period=base_period,
            current_period=current_period,
            route_indices=route_indices,
            quality_score=result.coverage_rate,
            data_source=data_source,
            flags=list(result.quality_flags),
            metadata={
                "engine": "real",
                "observation_count": len(observations),
                "observations_used": result.observations_used,
                "coverage_rate": result.coverage_rate,
            },
        )

    def get_timeseries(self, start_date: str, end_date: str) -> List[TimeseriesPoint]:
        periods = self._month_range(start_date, end_date)
        if not periods:
            return []

        observations, is_real_data = data_access.load_validated_observations()
        df = pd.DataFrame(observations)
        weights, _weights_real = _build_weights(observations)
        data_periods = data_access.available_periods(observations)
        base_period = data_periods[0] if data_periods else periods[0]

        def index_for(period: str) -> Optional[float]:
            try:
                result = _calculate(df, weights, base_period, period)
            except Exception:
                return None
            return result.national_index

        points: List[TimeseriesPoint] = []
        for i, period in enumerate(periods):
            current_idx = index_for(period)
            if current_idx is None:
                # No real coverage for this specific month -- fall back to
                # a deterministic, clearly-labeled synthetic point so the
                # response always has one point per requested month (the
                # documented contract), never a gap.
                current_idx = 100.0 + 0.8 * i
                point_source = "synthetic"
            else:
                point_source = "real" if is_real_data else "synthetic"

            prev_month_idx = index_for(shift_period(period, -1))
            prev_year_idx = index_for(shift_period(period, -12))
            mom = _safe_pct_change(current_idx if point_source != "synthetic" else None, prev_month_idx)
            yoy = _safe_pct_change(current_idx if point_source != "synthetic" else None, prev_year_idx)

            points.append(
                TimeseriesPoint(
                    period=period,
                    index=round(current_idx, 2),
                    mom=round(mom, 2) if mom is not None else None,
                    yoy=round(yoy, 2) if yoy is not None else None,
                    data_source=point_source,
                )
            )
        return points

    @staticmethod
    def _month_range(start_date: str, end_date: str) -> List[str]:
        periods = []
        current = start_date
        # Bounded loop: a malformed/huge range fails closed rather than spinning.
        for _ in range(1000):
            periods.append(current)
            if current >= end_date:
                break
            current = shift_period(current, 1)
        return periods


class RealDataQualityEngine:
    """Real implementation of ``DataQualityProtocol``."""

    def assess_quality(self, observations: Optional[List[Dict[str, Any]]] = None) -> QualityReport:
        if observations:
            raw = observations
            is_real = not all(o.get("is_mock", True) for o in observations)
        else:
            raw, is_real = data_access.load_raw_observations()

        result = data_quality_mod.validate_fare_batch(raw)
        data_source = "real" if is_real else "synthetic"

        route_health = [
            RouteHealth(
                route=rh.route,
                observations=rh.observations_total,
                # data_quality's own RouteHealth folds VALID+FLAGGED into
                # one "observations_valid" bucket at route granularity (see
                # its docstring) -- mirrored here rather than guessing a
                # flagged/valid split that doesn't exist at this level.
                valid=rh.observations_valid,
                rejected=rh.observations_rejected,
                flagged=0,
                health_score=rh.route_quality_rate,
                status=(
                    "healthy" if rh.route_quality_rate >= 0.9
                    else "degraded" if rh.route_quality_rate >= 0.6
                    else "critical"
                ),
            )
            for rh in result.route_health
        ]

        source_health = [
            SourceHealth(
                source=sh.source,
                observations=sh.observations_received,
                valid=sh.valid_observations,
                rejected=sh.rejected_observations,
                reliability_score=sh.observation_validity_rate,
            )
            for sh in result.source_health
        ]

        return QualityReport(
            total_observations=result.records_received,
            valid=result.records_valid,
            rejected=result.records_rejected,
            flagged=result.records_flagged,
            rejection_reasons=dict(result.rejection_reasons),
            quality_score=result.quality_score,
            quality_grade=result.quality_grade,
            route_health=route_health,
            source_health=source_health,
            data_source=data_source,
        )


class RealRouteAnalyticsEngine:
    """Real implementation of ``RouteAnalyticsProtocol``."""

    def get_route_analysis(self) -> List[RouteAnalysis]:
        observations, is_real_data = data_access.load_validated_observations()
        base_period, current_period = _period_bounds(observations)
        df = pd.DataFrame(observations)
        weights, weights_real = _build_weights(observations)

        current = _calculate(df, weights, base_period, current_period)
        prev_month_period = shift_period(current_period, -1)
        try:
            prev_month = _calculate(df, weights, base_period, prev_month_period)
            prev_by_route = {r.route: r for r in prev_month.route_indices}
        except Exception:
            prev_by_route = {}

        contribution_by_route = {c.route: c.contribution_points for c in current.route_contributions}
        data_source = "real" if (is_real_data and weights_real) else "synthetic"

        status_map = {"OK": "active", "NEW_ROUTE": "new"}

        results = []
        for ri in current.route_indices:
            prev = prev_by_route.get(ri.route)
            mom = (
                _safe_pct_change(ri.route_index, prev.route_index)
                if ri.status == "OK" and prev is not None and prev.status == "OK"
                else None
            )
            results.append(
                RouteAnalysis(
                    route=ri.route,
                    route_index=ri.route_index if ri.route_index is not None else 0.0,
                    mom=round(mom, 2) if mom is not None else None,
                    weight=ri.weight_normalized or 0.0,
                    contribution=contribution_by_route.get(ri.route) or 0.0,
                    traffic_coverage=ri.weight_normalized or 0.0,
                    status=status_map.get(ri.status, "inactive"),
                    data_source=data_source,
                )
            )
        return results


class RealNewsContextEngine:
    """Real implementation of ``NewsContextProtocol``.

    Wired to the real ``NewsContextService`` and route-movement
    computation, but backed by ``MockNewsProvider`` -- no real news API
    is connected anywhere in this project yet (see news_provider.py).
    Every response is therefore honestly labeled "synthetic" regardless
    of whether the underlying fare data is real; see module docstring.
    """

    def __init__(self) -> None:
        self._service = NewsContextService(provider=MockNewsProvider())

    async def get_route_context(self, route_code: str) -> RouteContext:
        observations, _is_real_data = data_access.load_validated_observations()
        base_period, current_period = _period_bounds(observations)
        df = pd.DataFrame(observations)
        weights, _weights_real = _build_weights(observations)

        current = _calculate(df, weights, base_period, current_period)
        current_ri = next((r for r in current.route_indices if r.route == route_code), None)
        if current_ri is None:
            raise ValueError(f"Unknown route: {route_code}")

        prev_month_period = shift_period(current_period, -1)
        try:
            prev_month = _calculate(df, weights, base_period, prev_month_period)
            prev_ri = next((r for r in prev_month.route_indices if r.route == route_code), None)
        except Exception:
            prev_ri = None

        row = RouteInflationRow(
            route=current_ri.route,
            origin=current_ri.origin,
            destination=current_ri.destination,
            current_index=current_ri.route_index,
            mom_inflation_pct=(
                _safe_pct_change(current_ri.route_index, prev_ri.route_index)
                if current_ri.status == "OK" and prev_ri is not None and prev_ri.status == "OK"
                else None
            ),
            yoy_inflation_pct=None,
            weight=current_ri.weight_normalized,
            traffic_weight=None,
            contribution=None,
            volatility=None,
            status=current_ri.status,
        )

        movement = route_movement_from_row(row, period=current_period, as_of=_NEWS_DEMO_ANCHOR, metric="mom")
        if movement is None:
            return RouteContext(
                route=route_code,
                significant_movement=False,
                movement_direction=None,
                movement_pct=None,
                events=[],
                data_source=_NEWS_DATA_SOURCE,
            )

        context_result = self._service.get_context(movement)
        direction_map = {"increase": "up", "decrease": "down"}

        events = [
            NewsEvent(
                headline=match.article.headline,
                source=match.article.source,
                publication_date=match.article.published_at.date().isoformat(),
                url=match.article.url,
                relevance_score=match.relevance_score,
                data_source=_NEWS_DATA_SOURCE,
            )
            for match in context_result.matches
        ]

        return RouteContext(
            route=route_code,
            significant_movement=self._service.config.significance_threshold_pct <= abs(movement.change_pct),
            movement_direction=direction_map.get(movement.direction),
            movement_pct=movement.change_pct,
            events=events,
            data_source=_NEWS_DATA_SOURCE,
        )
