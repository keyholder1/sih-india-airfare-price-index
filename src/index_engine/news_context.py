"""News & Event Context layer.

Answers "why did airfare prices move?" with *contextual evidence*, never a
causal claim. This module is strictly downstream of the price index:

    AirfarePriceIndex -> route price movement -> significant movement?
        -> News/Event Context layer -> relevant articles/events -> dashboard

It is optional and additive. Nothing in this file is imported by
:mod:`index_engine.index`, :mod:`index_engine.aggregation`, or any other
module that computes the index itself, and nothing in this file mutates an
``IndexResult``, a ``RouteInflationRow``, or any other index output — it
only reads them. See docs/news_context.md for the full write-up, including
why claims are phrased as "coincided with" rather than "caused by".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from .context_signals import ContextSignalProvider, ContextSignalResult
from .news_matching import MatchingConfig, rank_articles
from .news_models import (
    DEMAND_SUPPLY_EVENT_TYPES,
    EventType,
    NewsContextResult,
    NewsMatch,
    RouteMovement,
)
from .news_provider import NewsProvider, NewsSearchQuery
from .route_analysis import RouteInflationRow

#: A route movement smaller than this (in absolute percentage points) is
#: not considered "significant" and, per the project brief, should not
#: trigger a news search at all — routine month-to-month noise doesn't need
#: an explanation.
DEFAULT_SIGNIFICANCE_THRESHOLD_PCT = 5.0

#: A small set of generic disruption keywords always added to a search, on
#: top of the route's own city names — these are the kind of terms a real
#: news API's free-text search benefits from regardless of route.
GENERIC_DISRUPTION_KEYWORDS = [
    "flight cancellation",
    "airline strike",
    "airport disruption",
    "capacity cut",
    "weather delay",
]

#: IATA code -> city name aliases used to build search keywords. Kept local
#: to this module (rather than reusing index_engine.geo_metadata, which is
#: explicitly documented as map-rendering-only data) so a change here can
#: never have any bearing on anything the index engine computes.
_AIRPORT_CITY_ALIASES: Dict[str, str] = {
    "BLR": "Bengaluru",
    "DEL": "Delhi",
    "BOM": "Mumbai",
    "HYD": "Hyderabad",
    "MAA": "Chennai",
    "CCU": "Kolkata",
    "PNQ": "Pune",
    "AMD": "Ahmedabad",
    "GOI": "Goa",
    "COK": "Kochi",
    "LKO": "Lucknow",
}


def is_significant_movement(change_pct: float, threshold_pct: float = DEFAULT_SIGNIFICANCE_THRESHOLD_PCT) -> bool:
    """Whether a route's % change is large enough to be worth explaining."""
    return abs(change_pct) >= threshold_pct


def route_movement_from_row(
    row: RouteInflationRow,
    period: str,
    as_of: Optional[datetime] = None,
    metric: str = "mom",
) -> Optional[RouteMovement]:
    """Build a :class:`RouteMovement` from an existing
    ``RouteInflationRow`` (see :mod:`index_engine.route_analysis`), which is
    already computed by the index engine — this never recomputes a
    percentage change itself. Returns ``None`` if the row has no value for
    the requested metric (e.g. a new/discontinued route)."""
    change_pct = row.mom_inflation_pct if metric == "mom" else row.yoy_inflation_pct
    if change_pct is None:
        return None
    return RouteMovement(
        route=row.route,
        origin=row.origin,
        destination=row.destination,
        change_pct=change_pct,
        metric=metric,  # type: ignore[arg-type]
        period=period,
        as_of=as_of or datetime.utcnow(),
    )


def _build_search_query(movement: RouteMovement, window_days: int) -> NewsSearchQuery:
    origin_city = _AIRPORT_CITY_ALIASES.get(movement.origin.upper(), movement.origin)
    destination_city = _AIRPORT_CITY_ALIASES.get(movement.destination.upper(), movement.destination)
    keywords = [movement.origin, movement.destination, origin_city, destination_city, movement.route] + GENERIC_DISRUPTION_KEYWORDS
    return NewsSearchQuery(
        keywords=keywords,
        start_date=movement.as_of - timedelta(days=window_days),
        end_date=movement.as_of + timedelta(days=window_days),
        airports=[movement.origin, movement.destination],
        routes=[movement.route],
    )


def _potential_factors(matches: List[NewsMatch]) -> List[EventType]:
    """Distinct event types across the surfaced matches, most-relevant
    match first, de-duplicated — this is the "potential related factors"
    list for the dashboard summary, deliberately worded as "potential" and
    never as "cause"."""
    seen: List[EventType] = []
    for m in matches:
        if m.article.event_type not in seen:
            seen.append(m.article.event_type)
    return seen


@dataclass
class NewsContextConfig:
    date_window_days: int = 10
    min_relevance: float = 0.35
    top_n: int = 5
    significance_threshold_pct: float = DEFAULT_SIGNIFICANCE_THRESHOLD_PCT

    def to_matching_config(self) -> MatchingConfig:
        return MatchingConfig(date_window_days=self.date_window_days, min_relevance=self.min_relevance, top_n=self.top_n)


class NewsContextService:
    """Main entry point: wires a :class:`NewsProvider` + matching config
    together and answers "what news might explain this route's movement".

    ``provider`` is whatever implements :class:`NewsProvider` — a
    :class:`~index_engine.mock_news_provider.MockNewsProvider` for tests/
    demos, or a real API-backed provider a teammate connects later. This
    class never inspects which one it was given.
    """

    def __init__(self, provider: NewsProvider, config: Optional[NewsContextConfig] = None) -> None:
        self.provider = provider
        self.config = config or NewsContextConfig()

    def get_context(self, movement: RouteMovement, airlines_on_route: Optional[Iterable[str]] = None) -> NewsContextResult:
        query = _build_search_query(movement, self.config.date_window_days)
        candidates = self.provider.search(query)
        matches = rank_articles(
            movement, candidates, airlines_on_route=airlines_on_route, config=self.config.to_matching_config()
        )
        return NewsContextResult(movement=movement, matches=matches, potential_factors=_potential_factors(matches))

    def get_context_for_row(
        self,
        row: RouteInflationRow,
        period: str,
        as_of: Optional[datetime] = None,
        metric: str = "mom",
        airlines_on_route: Optional[Iterable[str]] = None,
    ) -> Optional[NewsContextResult]:
        """Convenience path straight from a ``RouteInflationRow`` — returns
        ``None`` if the row has no movement for ``metric`` (e.g. new route),
        matching :func:`route_movement_from_row`."""
        movement = route_movement_from_row(row, period=period, as_of=as_of, metric=metric)
        if movement is None:
            return None
        return self.get_context(movement, airlines_on_route=airlines_on_route)


def attach_news_context(
    rows: List[RouteInflationRow],
    period: str,
    service: NewsContextService,
    as_of: Optional[datetime] = None,
    metric: str = "mom",
    threshold_pct: Optional[float] = None,
) -> Dict[str, NewsContextResult]:
    """Combined-analytics helper: given the route inflation table an
    ``AirfareAnalytics.calculate(...)`` call already produced, return news
    context only for routes whose movement is significant.

    Deliberately takes ``rows`` (plain data) rather than an
    ``AnalyticsResult``, so this module never needs to import
    :mod:`index_engine.analytics` and the dependency direction stays
    one-way: analytics can optionally call into this module, this module
    never needs to know analytics exists.
    """
    threshold = threshold_pct if threshold_pct is not None else service.config.significance_threshold_pct
    results: Dict[str, NewsContextResult] = {}
    for row in rows:
        change_pct = row.mom_inflation_pct if metric == "mom" else row.yoy_inflation_pct
        if change_pct is None or not is_significant_movement(change_pct, threshold):
            continue
        context = service.get_context_for_row(row, period=period, as_of=as_of, metric=metric)
        if context is not None:
            results[row.route] = context
    return results


class NewsContextSignalAdapter(ContextSignalProvider):
    """Adapts :class:`NewsContextService` to the generic
    :class:`~index_engine.context_signals.ContextSignalProvider` interface,
    so a future aggregator combining News + Weather + Capacity +
    Cancellations can treat this signal the same as every other one."""

    def __init__(self, service: NewsContextService, airlines_on_route: Optional[Iterable[str]] = None) -> None:
        self.service = service
        self.airlines_on_route = airlines_on_route

    def get_signal(self, movement: RouteMovement) -> ContextSignalResult:
        context = self.service.get_context(movement, airlines_on_route=self.airlines_on_route)
        summary = (
            f"{len(context.matches)} potentially related article(s) found"
            if context.matches
            else "No relevant articles found in the search window"
        )
        return ContextSignalResult(signal_name="news", items=[m.to_dict() for m in context.matches], summary=summary)


# ---------------------------------------------------------------------------
# Dashboard-ready formatting
# ---------------------------------------------------------------------------

_EVENT_TYPE_EMOJI: Dict[str, str] = {
    "FLIGHT_CANCELLATION": "❌",
    "CAPACITY_REDUCTION": "✈️",
    "WEATHER_DISRUPTION": "\U0001f327️",
    "AIRPORT_DISRUPTION": "\U0001f6ec",
    "AIRLINE_OPERATIONAL_ISSUE": "⚙️",
    "STRIKE": "\U0001f6a7",
    "REGULATORY_CHANGE": "\U0001f4dc",
    "FUEL_PRICE_CHANGE": "⛽",
    "GEOPOLITICAL_EVENT": "\U0001f30d",
    "OTHER": "ℹ️",
}

_EVENT_TYPE_LABEL: Dict[str, str] = {
    "FLIGHT_CANCELLATION": "Flight cancellations",
    "CAPACITY_REDUCTION": "Capacity reduction",
    "WEATHER_DISRUPTION": "Weather disruption",
    "AIRPORT_DISRUPTION": "Airport disruption",
    "AIRLINE_OPERATIONAL_ISSUE": "Airline operational issue",
    "STRIKE": "Strike",
    "REGULATORY_CHANGE": "Regulatory change",
    "FUEL_PRICE_CHANGE": "Fuel price change",
    "GEOPOLITICAL_EVENT": "Geopolitical event",
    "OTHER": "Other",
}


def to_dashboard_dict(result: NewsContextResult) -> dict:
    """Structured, frontend-ready shape — one JSON object a dashboard
    component can render directly. Every entry under ``related_news``
    carries the untouched original publisher ``url``."""
    m = result.movement
    return {
        "route": m.route,
        "origin": m.origin,
        "destination": m.destination,
        "change_pct": m.change_pct,
        "direction": m.direction,
        "metric": m.metric,
        "period": m.period,
        "potential_related_factors": [
            {"event_type": et, "label": _EVENT_TYPE_LABEL.get(et, et), "emoji": _EVENT_TYPE_EMOJI.get(et, "")}
            for et in result.potential_factors
        ],
        "related_news": [
            {
                "headline": nm.article.headline,
                "source": nm.article.source,
                "published_at": nm.article.published_at.isoformat(),
                "url": nm.article.url,
                "summary": nm.article.summary,
                "event_type": nm.article.event_type,
                "relevance_score": nm.relevance_score,
                "confidence_score": nm.article.confidence_score,
                "is_mock": nm.article.is_mock,
            }
            for nm in result.matches
        ],
        "disclaimer": result.disclaimer,
    }


def to_dashboard_text(result: NewsContextResult) -> str:
    """Human-readable rendering matching the project brief's mockup, e.g.::

        AIRFARE SPIKE
        BLR -> DEL
        +14.2%

        Potential related factors:

        [emoji] Capacity reduction
        [emoji] Weather disruption

        Related news:

        1. Headline
           Reuters . 14 Aug 2026
           Read original article -> https://...
    """
    m = result.movement
    label = "AIRFARE SPIKE" if m.direction == "increase" else "AIRFARE DROP"
    lines = [label, f"{m.origin} -> {m.destination}", f"{m.change_pct:+.1f}%", ""]

    if result.potential_factors:
        lines.append("Potential related factors:")
        lines.append("")
        for et in result.potential_factors:
            emoji = _EVENT_TYPE_EMOJI.get(et, "")
            lines.append(f"{emoji} {_EVENT_TYPE_LABEL.get(et, et)}".strip())
        lines.append("")

    if result.matches:
        lines.append("Related news:")
        lines.append("")
        for i, nm in enumerate(result.matches, start=1):
            a = nm.article
            date_str = a.published_at.strftime("%d %b %Y")
            lines.append(f"{i}. {a.headline}")
            lines.append(f"   {a.source} . {date_str}")
            lines.append(f"   Read original article -> {a.url}")
            lines.append("")
    else:
        lines.append("Related news: none found in the search window.")
        lines.append("")

    lines.append(result.disclaimer)
    return "\n".join(lines)
