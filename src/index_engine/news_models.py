"""Typed data structures for the News & Event Context layer.

Deliberately mirrors the style of :mod:`index_engine.models`: plain
dataclasses with a ``to_dict()``, no dependency beyond the standard library,
so this can be serialized by whatever the backend ends up using.

Nothing in this module performs a statistical calculation and nothing here
is consumed by :mod:`index_engine.index` or :mod:`index_engine.aggregation`.
The dependency only ever runs one way: news context reads a route's already
-computed movement, it never feeds back into it. See docs/news_context.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional
from urllib.parse import urlparse

#: Controlled vocabulary for what kind of real-world event an article
#: describes. Kept as a ``Literal`` (not an ``enum.Enum``) to match the rest
#: of this package's convention (see ``RepresentativeMethod`` in config.py).
EventType = Literal[
    "FLIGHT_CANCELLATION",
    "CAPACITY_REDUCTION",
    "WEATHER_DISRUPTION",
    "AIRPORT_DISRUPTION",
    "AIRLINE_OPERATIONAL_ISSUE",
    "STRIKE",
    "REGULATORY_CHANGE",
    "FUEL_PRICE_CHANGE",
    "GEOPOLITICAL_EVENT",
    "OTHER",
]

EVENT_TYPES: tuple = (
    "FLIGHT_CANCELLATION",
    "CAPACITY_REDUCTION",
    "WEATHER_DISRUPTION",
    "AIRPORT_DISRUPTION",
    "AIRLINE_OPERATIONAL_ISSUE",
    "STRIKE",
    "REGULATORY_CHANGE",
    "FUEL_PRICE_CHANGE",
    "GEOPOLITICAL_EVENT",
    "OTHER",
)

#: Event types that plausibly explain a short-term fare movement on their
#: own (used only to lightly re-rank candidate articles — never to decide
#: whether an article is "true" or to alter any index number).
DEMAND_SUPPLY_EVENT_TYPES: tuple = (
    "FLIGHT_CANCELLATION",
    "CAPACITY_REDUCTION",
    "WEATHER_DISRUPTION",
    "AIRPORT_DISRUPTION",
    "AIRLINE_OPERATIONAL_ISSUE",
    "STRIKE",
)


@dataclass
class NewsArticle:
    """One real-world news article, as returned by a :class:`NewsProvider`.

    ``url`` must always be the original publisher's link — this layer never
    stores or serves copied article text, only a short ``summary``/snippet.
    ``is_mock`` must be ``True`` for anything produced by
    :class:`MockNewsProvider` so mock and real data can never be confused
    downstream.
    """

    headline: str
    source: str
    published_at: datetime
    url: str
    event_type: EventType
    summary: Optional[str] = None
    related_airlines: List[str] = field(default_factory=list)
    related_airports: List[str] = field(default_factory=list)
    related_routes: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None
    is_mock: bool = False

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"event_type must be one of {EVENT_TYPES}, got {self.event_type!r}")
        if not self.url:
            raise ValueError("NewsArticle.url must be the original publisher URL and cannot be empty")
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"NewsArticle.url must be an absolute http(s) URL pointing at the original publisher, "
                f"got {self.url!r}"
            )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat()
        return d


@dataclass
class RouteMovement:
    """The input this layer reacts to: a route's already-computed price
    movement. Built from ``index_engine`` output (typically a
    ``RouteInflationRow``) — never recomputed here.
    """

    route: str
    origin: str
    destination: str
    change_pct: float
    metric: Literal["mom", "yoy"]
    period: str
    as_of: datetime

    @property
    def direction(self) -> Literal["increase", "decrease"]:
        return "increase" if self.change_pct >= 0 else "decrease"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        d["direction"] = self.direction
        return d


@dataclass
class NewsMatch:
    """One article matched to a :class:`RouteMovement`, with the score and
    the reasons it matched — kept together so a dashboard/debugging view
    never has to guess why an article was surfaced."""

    article: NewsArticle
    relevance_score: float
    matched_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "article": self.article.to_dict(),
            "relevance_score": self.relevance_score,
            "matched_signals": self.matched_signals,
        }


CAUSATION_DISCLAIMER = (
    "This is contextual evidence only, not a causal explanation. The events "
    "below coincided with the observed airfare movement in date and route/"
    "airport/airline overlap; they are not confirmed causes."
)


@dataclass
class NewsContextResult:
    """Full output of matching news to one route's price movement."""

    movement: RouteMovement
    matches: List[NewsMatch]
    potential_factors: List[EventType]
    disclaimer: str = CAUSATION_DISCLAIMER

    def to_dict(self) -> dict:
        return {
            "movement": self.movement.to_dict(),
            "matches": [m.to_dict() for m in self.matches],
            "potential_factors": self.potential_factors,
            "disclaimer": self.disclaimer,
        }
