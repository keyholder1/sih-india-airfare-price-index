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

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from index_engine import AirfarePriceIndex
from index_engine.composite_news_provider import CompositeNewsProvider
from index_engine.eonet_client import EonetClient
from index_engine.eonet_context import CATEGORY_EMOJI, CATEGORY_LABELS, EonetContextService
from index_engine.eventregistry_news_provider import ENV_API_KEY as EVENTREGISTRY_ENV_API_KEY, EventRegistryNewsProvider
from index_engine.gdelt_news_provider import GdeltNewsProvider
from index_engine.mock_news_provider import MockNewsProvider
from index_engine.news_context import NewsContextService, route_movement_from_row
from index_engine.news_provider import NewsProvider
from index_engine.newsapi_org_news_provider import ENV_API_KEY as NEWSAPI_ORG_ENV_API_KEY, NewsApiOrgProvider
from index_engine.newsdata_news_provider import ENV_API_KEY as NEWSDATA_ENV_API_KEY, NewsdataNewsProvider
from index_engine.route_analysis import RouteInflationRow
from index_engine.openweather_client import OpenWeatherClient
from index_engine.utils import pct_change, shift_period
from index_engine.weather_context import WeatherContextService

import data_quality as data_quality_mod

from src.engine import data_access
from src.engine.news_cache_provider import CachingNewsProvider
from src.engine.protocols import (
    IndexResult,
    NaturalEventContext,
    NewsEvent,
    QualityReport,
    RouteAnalysis,
    RouteContext,
    RouteHealth,
    RouteIndex,
    SourceHealth,
    TimeseriesPoint,
    WeatherSnapshot,
)

REPO_ROOT = data_access.REPO_ROOT

#: News provider selection: NEWS_PROVIDER=mock forces the deterministic
#: fixture provider (the test suite does this -- see tests/conftest.py --
#: so pytest never depends on a live network call). Otherwise every real
#: source with a configured key (newsdata.io, NewsAPI.org, Event
#: Registry/newsapi.ai) is queried together via CompositeNewsProvider --
#: relevance ranking in news_matching is the only thing deciding which
#: articles surface, not which key happened to find them -- falling back
#: to GDELT (free, keyless, but not always reachable from every network)
#: only if none of the keyed sources are configured. The whole thing is
#: wrapped in a one-week Postgres cache (CachingNewsProvider) so looking
#: at the same route repeatedly doesn't re-spend any of those keys'
#: quota. MockNewsProvider's fixture data is anchored around 2026-08-14
#: (see that module's docstring) -- the mock path needs its `as_of` to
#: match that fixed window; every real path searches around the actual
#: current time.
_USE_MOCK_NEWS = os.environ.get("NEWS_PROVIDER", "").lower() == "mock"
_MOCK_NEWS_ANCHOR = datetime(2026, 8, 14, 9, 0, 0)  # naive, matches DEMO_ARTICLES


class _OfflineHttpClient:
    """Stands in for httpx.Client when NEWS_PROVIDER=mock -- every call
    fails immediately with no real socket/DNS activity, so
    EonetClient/OpenWeatherClient take the exact same "network failed"
    code path they'd take for a genuine outage (degrading to their own
    UNAVAILABLE status), without ever making a live call. Same reasoning
    as MockNewsProvider existing to keep GDELT out of the test suite --
    EONET (keyless) and OpenWeatherMap have no equivalent mock provider
    of their own, so this is the mechanism that keeps them out instead."""

    def get(self, url: str, params: Optional[dict] = None):  # noqa: ARG002
        import httpx

        raise httpx.ConnectError("NEWS_PROVIDER=mock -- EONET/weather network calls are disabled in test/mock mode.")

    def close(self) -> None:
        pass


def _default_news_provider() -> NewsProvider:
    keyed_providers: List[NewsProvider] = []
    if os.environ.get(NEWSDATA_ENV_API_KEY):
        keyed_providers.append(NewsdataNewsProvider())
    if os.environ.get(NEWSAPI_ORG_ENV_API_KEY):
        keyed_providers.append(NewsApiOrgProvider())
    if os.environ.get(EVENTREGISTRY_ENV_API_KEY):
        keyed_providers.append(EventRegistryNewsProvider())

    inner: NewsProvider = CompositeNewsProvider(keyed_providers) if keyed_providers else GdeltNewsProvider()
    return CachingNewsProvider(inner)


def _letter_grade(score_0_100: float) -> str:
    """data_quality.compute_quality_score returns a 0-100 score with its
    own PROTOTYPE grade words (see scoring.py); the API contract wants a
    0-1 score and an A-F letter, so both are re-derived from the numeric
    score here using standard bands rather than trying to keep two grade
    vocabularies in sync."""
    if score_0_100 >= 90:
        return "A"
    if score_0_100 >= 80:
        return "B"
    if score_0_100 >= 70:
        return "C"
    if score_0_100 >= 60:
        return "D"
    return "F"


def _safe_pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return pct_change(current, previous)


def _period_bounds(observations: List[Dict[str, Any]]) -> tuple[str, str]:
    periods = data_access.available_periods(observations)
    if not periods:
        raise ValueError("No periods available in the loaded observation set.")
    return periods[0], periods[-1]


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
                # Never fabricated: a route with no computable index (e.g.
                # no base-period fare) reports null, not a fake 0.0 --
                # 0.0 would read as a measured 100-point fare crash.
                index=ri.route_index,
                mom=None,  # not computed for this single-shot call; see get_timeseries for MoM
                weight=ri.weight_normalized or 0.0,
                contribution=contribution_by_route.get(ri.route) or 0.0,
                data_source=data_source,
            )
            for ri in result.route_indices
        ]

        return IndexResult(
            # Never fabricated: no coverage means null, not a fake 100.0
            # baseline that would read as a real "no change" measurement.
            national_index=result.national_index,
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

        observations, provenance = data_access.load_validated_observations()
        df = pd.DataFrame(observations)
        weights, _weights_real = data_access.build_weights(observations)
        data_periods = data_access.available_periods(observations)
        base_period = data_periods[0] if data_periods else periods[0]

        def index_for(period: str) -> Optional[float]:
            try:
                result = _calculate(df, weights, base_period, period)
            except Exception:
                return None
            return result.national_index

        points: List[TimeseriesPoint] = []
        for period in periods:
            current_idx = index_for(period)
            if current_idx is None:
                # No coverage for this specific month -- a missing month
                # is not an index value. Report it as such rather than
                # drawing a fake, plausible-looking measurement.
                points.append(
                    TimeseriesPoint(
                        period=period,
                        index=None,
                        mom=None,
                        yoy=None,
                        data_source=data_access.PROVENANCE_UNAVAILABLE.lower(),
                    )
                )
                continue

            point_source = provenance.lower()
            prev_month_idx = index_for(shift_period(period, -1))
            prev_year_idx = index_for(shift_period(period, -12))
            mom = _safe_pct_change(current_idx, prev_month_idx)
            yoy = _safe_pct_change(current_idx, prev_year_idx)

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
            provenance = data_access.classify_provenance(observations)
        else:
            raw, provenance = data_access.load_raw_observations()

        result = data_quality_mod.validate_fare_batch(raw)
        data_source = provenance.lower()

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
            quality_score=round(result.quality_score / 100.0, 4),
            quality_grade=_letter_grade(result.quality_score),
            route_health=route_health,
            source_health=source_health,
            data_source=data_source,
        )


class RealRouteAnalyticsEngine:
    """Real implementation of ``RouteAnalyticsProtocol``."""

    def get_route_analysis(self) -> List[RouteAnalysis]:
        observations, provenance = data_access.load_validated_observations()
        base_period, current_period = _period_bounds(observations)
        df = pd.DataFrame(observations)
        weights, weights_real = data_access.build_weights(observations)

        current = _calculate(df, weights, base_period, current_period)
        prev_month_period = shift_period(current_period, -1)
        try:
            prev_month = _calculate(df, weights, base_period, prev_month_period)
            prev_by_route = {r.route: r for r in prev_month.route_indices}
        except Exception:
            prev_by_route = {}

        contribution_by_route = {c.route: c.contribution_points for c in current.route_contributions}
        # weights_real=False (equal-weight fallback, not DGCA-derived)
        # still taints the result to synthetic regardless of observation
        # provenance; otherwise report the observations' own provenance
        # (REAL/SYNTHETIC/MIXED/UNAVAILABLE) -- never collapse MIXED into
        # "real".
        data_source = provenance.lower() if weights_real else "synthetic"

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
                    # Never fabricated: a route with no computable index
                    # reports null, not a fake 0.0.
                    route_index=ri.route_index,
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
    computation. See module docstring for provider selection (newsdata.io
    if NEWSDATA_API_KEY is set, else GDELT, else MockNewsProvider in
    tests). Each event is labeled "real"/"synthetic" from its own
    article's is_mock flag, not a fixed constant, so a mixed-mode
    response is never mislabeled either way.
    """

    def __init__(
        self,
        provider: Optional[NewsProvider] = None,
        eonet_service: Optional[EonetContextService] = None,
        weather_service: Optional[WeatherContextService] = None,
    ) -> None:
        if provider is not None:
            self._provider = provider
        elif _USE_MOCK_NEWS:
            self._provider = MockNewsProvider()
        else:
            self._provider = _default_news_provider()
        self._service = NewsContextService(provider=self._provider)
        # EONET/weather have no fabricated-content mock provider of their
        # own (unlike news' MockNewsProvider) -- when NEWS_PROVIDER=mock
        # (the test suite's default, see tests/conftest.py), both are
        # wired to an offline stub instead so this endpoint never makes a
        # real network call from an automated test, same discipline as
        # avoiding GDELT there. Each degrades to its own honest
        # "unavailable" state either way -- see docs/eonet_context.md
        # "Failure isolation".
        if eonet_service is not None:
            self._eonet_service = eonet_service
        elif _USE_MOCK_NEWS:
            self._eonet_service = EonetContextService(client=EonetClient(client=_OfflineHttpClient()))
        else:
            self._eonet_service = EonetContextService()

        if weather_service is not None:
            self._weather_service = weather_service
        elif _USE_MOCK_NEWS:
            self._weather_service = WeatherContextService(client=OpenWeatherClient(client=_OfflineHttpClient()))
        else:
            self._weather_service = WeatherContextService()

    def _safe_eonet_context(self, movement):
        """Sync wrapper offloaded via asyncio.to_thread (see
        get_route_context) -- EONET must never prevent this endpoint
        from returning a valid response, see docs/eonet_context.md
        "Failure isolation". The service itself already never raises;
        this is a second, deliberate layer at the actual
        dashboard-facing seam."""
        try:
            return self._eonet_service.get_context(movement)
        except Exception as exc:  # noqa: BLE001
            from index_engine.eonet_context import EonetContextResult

            return EonetContextResult(movement=movement, matches=[], status="UNAVAILABLE", error_detail=f"{type(exc).__name__}: {exc}")

    def _safe_weather_context(self, origin: str, destination: str):
        """Sync wrapper offloaded via asyncio.to_thread (see
        get_route_context) -- same failure-isolation reasoning as
        _safe_eonet_context."""
        try:
            return self._weather_service.get_route_weather(origin, destination)
        except Exception as exc:  # noqa: BLE001
            from index_engine.weather_models import RouteWeatherContext

            return RouteWeatherContext(
                route=f"{origin}-{destination}", origin=None, destination=None, status="UNAVAILABLE", error_detail=f"{type(exc).__name__}: {exc}"
            )

    async def get_route_context(self, route_code: str) -> RouteContext:
        observations, _is_real_data = data_access.load_validated_observations()
        base_period, current_period = _period_bounds(observations)
        df = pd.DataFrame(observations)
        weights, _weights_real = data_access.build_weights(observations)

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

        as_of = _MOCK_NEWS_ANCHOR if _USE_MOCK_NEWS else datetime.utcnow()
        movement = route_movement_from_row(row, period=current_period, as_of=as_of, metric="mom")
        overall_data_source = "synthetic" if _USE_MOCK_NEWS else "real"
        if movement is None:
            return RouteContext(
                route=route_code,
                significant_movement=False,
                movement_direction=None,
                movement_pct=None,
                events=[],
                data_source=overall_data_source,
            )

        # News/EONET/weather each make real, potentially multi-second
        # blocking network calls (httpx.Client, synchronous). Run all
        # three concurrently in worker threads (asyncio.to_thread) rather
        # than sequentially inline -- calling blocking I/O directly
        # inside this async function would freeze the single event loop
        # for its entire duration, stalling every *other* request the
        # server is handling (including unrelated ones like GET
        # /api/v1/analytics) until it returns. Also meaningfully faster:
        # total latency becomes roughly max(news, eonet, weather) instead
        # of their sum.
        context_result, eonet_result, weather_result = await asyncio.gather(
            asyncio.to_thread(self._service.get_context, movement),
            asyncio.to_thread(self._safe_eonet_context, movement),
            asyncio.to_thread(self._safe_weather_context, current_ri.origin, current_ri.destination),
        )
        direction_map = {"increase": "up", "decrease": "down"}

        events = [
            NewsEvent(
                headline=match.article.headline,
                source=match.article.source,
                publication_date=match.article.published_at.date().isoformat(),
                url=match.article.url,
                relevance_score=match.relevance_score,
                data_source="synthetic" if match.article.is_mock else "real",
            )
            for match in context_result.matches
        ]

        natural_events = [
            NaturalEventContext(
                event_id=m.event.event_id,
                title=m.event.title,
                category=m.event.category,
                category_label=CATEGORY_LABELS.get(m.event.category, m.event.category),
                category_emoji=CATEGORY_EMOJI.get(m.event.category, ""),
                event_date=m.event.event_date.isoformat(),
                distance_from_origin_km=m.distance_from_origin_km,
                distance_from_destination_km=m.distance_from_destination_km,
                temporal_distance_days=m.temporal_distance_days,
                relevance_score=m.relevance_score,
                relevance_reason=m.relevance_reason,
                source_url=m.event.source_url,
                is_closed=m.event.is_closed,
            )
            for m in eonet_result.matches
        ]

        def _weather_snapshot(w) -> Optional[WeatherSnapshot]:
            if w is None:
                return None
            return WeatherSnapshot(
                iata_code=w.iata_code,
                city_name=w.city_name,
                observed_at=w.observed_at.isoformat(),
                temperature_c=w.temperature_c,
                feels_like_c=w.feels_like_c,
                condition=w.condition,
                description=w.description,
                wind_speed_ms=w.wind_speed_ms,
                humidity_pct=w.humidity_pct,
                visibility_m=w.visibility_m,
            )

        return RouteContext(
            route=route_code,
            significant_movement=self._service.config.significance_threshold_pct <= abs(movement.change_pct),
            movement_direction=direction_map.get(movement.direction),
            movement_pct=movement.change_pct,
            events=events,
            data_source=overall_data_source,
            natural_events=natural_events,
            natural_events_status=eonet_result.status,
            weather_origin=_weather_snapshot(weather_result.origin),
            weather_destination=_weather_snapshot(weather_result.destination),
            weather_status=weather_result.status,
        )
