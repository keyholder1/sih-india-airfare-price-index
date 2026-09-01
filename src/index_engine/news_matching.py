"""Relevance scoring: how well does a candidate article explain a given
route's price movement?

This is a heuristic, explainable scoring function — not a machine-learning
model and not part of the price index. It combines the signals called out
in the project brief:

1. date/time proximity to the movement's period
2. airport mention (origin and/or destination)
3. airline mention (bonus if the airline is known to operate the route)
4. route mention (both airports named together, or an explicit route tag)
5. event type (some event types plausibly explain a fare move; others
   rarely do, e.g. a regulatory-change article about an unrelated topic)
6. geographic relevance (a nationwide event still plausibly touches any
   route; an event tied to airports unrelated to this route does not)

Every signal is a bounded [0, 1] score; the total is a weighted sum, also
bounded to [0, 1]. Nothing here compares fares or touches the index.

Note: signals 2 (airport) and 6 (geographic) are correlated, not fully
independent — both key off ``article.related_airports`` overlapping this
route's origin/destination. An article naming this route's specific
airports gets credit under both (combined weight 0.35), which is a
deliberate emphasis on airport-specific news, not an accidental double
-count of six independent inputs — worth knowing when tuning the weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from .news_models import DEMAND_SUPPLY_EVENT_TYPES, NewsArticle, NewsMatch, RouteMovement

#: Relative weight of each signal. Kept as named constants (not magic
#: numbers inline) so the scoring can be re-tuned without touching the
#: scoring logic itself.
WEIGHT_DATE_PROXIMITY = 0.25
WEIGHT_AIRPORT = 0.25
WEIGHT_ROUTE = 0.15
WEIGHT_AIRLINE = 0.15
WEIGHT_EVENT_TYPE = 0.10
WEIGHT_GEOGRAPHIC = 0.10

DEFAULT_DATE_WINDOW_DAYS = 10
DEFAULT_MIN_RELEVANCE = 0.35


@dataclass
class MatchingConfig:
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS
    min_relevance: float = DEFAULT_MIN_RELEVANCE
    top_n: int = 5

    def __post_init__(self) -> None:
        if self.date_window_days <= 0:
            raise ValueError("date_window_days must be positive")
        if not 0.0 <= self.min_relevance <= 1.0:
            raise ValueError("min_relevance must be in [0, 1]")
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")


def _normalize(values: Iterable[str]) -> set:
    return {v.strip().upper() for v in values if v}


def _as_utc(dt: datetime) -> datetime:
    """Normalize to a timezone-aware UTC datetime so two datetimes can
    always be subtracted, regardless of whether either side is naive or
    aware. A naive datetime is assumed to already be UTC (matching how
    ``RouteMovement.as_of`` and ``MockNewsProvider``'s fixture data are
    constructed) rather than the local timezone — never assume local time
    for data that may have come from a server-side pipeline."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _date_proximity_score(article: NewsArticle, movement: RouteMovement, window_days: int) -> float:
    delta_days = abs((_as_utc(article.published_at) - _as_utc(movement.as_of)).total_seconds()) / 86400.0
    if delta_days >= window_days:
        return 0.0
    return max(0.0, 1.0 - (delta_days / window_days))


def _airport_score(article: NewsArticle, movement: RouteMovement) -> tuple:
    article_airports = _normalize(article.related_airports)
    origin_hit = movement.origin.upper() in article_airports
    destination_hit = movement.destination.upper() in article_airports
    hits = sum([origin_hit, destination_hit])
    score = hits / 2.0
    signals = []
    if origin_hit:
        signals.append("airport:origin")
    if destination_hit:
        signals.append("airport:destination")
    return score, signals


def _route_score(article: NewsArticle, movement: RouteMovement) -> tuple:
    article_routes = _normalize(article.related_routes)
    forward = movement.route.upper()
    reverse = f"{movement.destination}-{movement.origin}".upper()
    if forward in article_routes or reverse in article_routes:
        return 1.0, ["route"]
    return 0.0, []


def _airline_score(article: NewsArticle, airlines_on_route: Optional[Iterable[str]]) -> tuple:
    article_airlines = _normalize(article.related_airlines)
    if not article_airlines:
        return 0.0, []
    if airlines_on_route is not None:
        known = _normalize(airlines_on_route)
        if article_airlines & known:
            return 1.0, ["airline:operates_route"]
        # An airline is named, but not one known to operate this route —
        # weak signal only (could still be a codeshare/partner we don't
        # have data for), not zero.
        return 0.25, ["airline:unrelated"]
    # No route-airline roster supplied — any named airline is a mild signal.
    return 0.5, ["airline:mentioned"]


def _event_type_score(article: NewsArticle) -> tuple:
    if article.event_type in DEMAND_SUPPLY_EVENT_TYPES:
        return 1.0, [f"event_type:{article.event_type}"]
    if article.event_type == "OTHER":
        return 0.0, []
    return 0.5, [f"event_type:{article.event_type}"]


def _geographic_score(article: NewsArticle, movement: RouteMovement) -> tuple:
    article_airports = _normalize(article.related_airports)
    if not article_airports:
        # No specific airport named (e.g. a national fuel-price or
        # regulatory story) — still plausibly relevant to any route.
        return 0.5, ["geographic:national"]
    if movement.origin.upper() in article_airports or movement.destination.upper() in article_airports:
        return 1.0, ["geographic:route_specific"]
    # Names specific airports, and none of them are this route's.
    return 0.0, []


def score_article(
    article: NewsArticle,
    movement: RouteMovement,
    airlines_on_route: Optional[Iterable[str]] = None,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> NewsMatch:
    """Score one article against one route movement. Pure function, no
    side effects, no mutation of either input."""
    signals: List[str] = []

    date_score = _date_proximity_score(article, movement, date_window_days)
    if date_score > 0:
        signals.append("date_proximity")

    airport_score, airport_signals = _airport_score(article, movement)
    signals.extend(airport_signals)

    route_score, route_signals = _route_score(article, movement)
    signals.extend(route_signals)

    airline_score, airline_signals = _airline_score(article, airlines_on_route)
    signals.extend(airline_signals)

    event_score, event_signals = _event_type_score(article)
    signals.extend(event_signals)

    geo_score, geo_signals = _geographic_score(article, movement)
    signals.extend(geo_signals)

    total = (
        WEIGHT_DATE_PROXIMITY * date_score
        + WEIGHT_AIRPORT * airport_score
        + WEIGHT_ROUTE * route_score
        + WEIGHT_AIRLINE * airline_score
        + WEIGHT_EVENT_TYPE * event_score
        + WEIGHT_GEOGRAPHIC * geo_score
    )
    total = max(0.0, min(1.0, total))

    return NewsMatch(article=article, relevance_score=round(total, 4), matched_signals=signals)


def rank_articles(
    movement: RouteMovement,
    articles: Iterable[NewsArticle],
    airlines_on_route: Optional[Iterable[str]] = None,
    config: Optional[MatchingConfig] = None,
) -> List[NewsMatch]:
    """Score every candidate article and return the top matches above
    ``config.min_relevance``, highest relevance first. Ties broken by more
    recent publication.

    Candidates are de-duplicated by ``url`` first (keeping the first
    occurrence) — a provider returning the same article twice (or two
    providers returning the same wire-service story) should not let one
    article occupy two of the ``top_n`` slots."""
    config = config or MatchingConfig()
    deduped: List[NewsArticle] = []
    seen_urls = set()
    for a in articles:
        if a.url in seen_urls:
            continue
        seen_urls.add(a.url)
        deduped.append(a)

    matches = [
        score_article(a, movement, airlines_on_route=airlines_on_route, date_window_days=config.date_window_days)
        for a in deduped
    ]
    matches = [m for m in matches if m.relevance_score >= config.min_relevance]
    matches.sort(key=lambda m: (m.relevance_score, m.article.published_at), reverse=True)
    return matches[: config.top_n]
