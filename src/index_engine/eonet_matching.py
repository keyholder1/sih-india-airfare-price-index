"""Geographic + temporal relevance scoring: how plausibly does a real
EONET natural event provide context for a given route's price movement?

Mirrors news_matching.py's approach -- a heuristic, explainable,
weighted-signal score, not a machine-learning model and not part of the
price index. Two signals, both real/measurable (unlike news matching's
string-based airport/route mentions, EONET gives real coordinates):

1. geographic proximity -- haversine distance (km) from the event to the
   route's origin AND destination airports (index_engine.geo_metadata's
   real CITY_COORDINATES); the closer of the two counts.
2. temporal proximity -- days between the event's date and the route
   movement's `as_of`, linear decay within a configurable window, same
   shape as news_matching's date-proximity signal.

Both bounds (EVENT_RADIUS_KM, EVENT_TIME_WINDOW_DAYS) are named
constants, not magic numbers, and both are caller-configurable via
EonetMatchingConfig. An event outside BOTH the radius and the window
scores 0 -- it is not "somewhat relevant," it is not relevant at all
under this rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from .eonet_models import NaturalEvent, NaturalEventMatch
from .geo_metadata import CITY_COORDINATES
from .news_models import RouteMovement  # reused, not duplicated -- see module docstring

#: Radius within which an event is considered geographically close
#: enough to a route's airport to plausibly be relevant. Documented, not
#: arbitrary: ~300km covers "affects the metro area and its usual
#: catchment" (e.g. a cyclone making landfall near a city, a wildfire in
#: the surrounding region) without stretching to "somewhere in the same
#: half of the country."
DEFAULT_EVENT_RADIUS_KM = 300.0

#: Days on either side of the route movement's `as_of` within which an
#: event is considered temporally close enough to plausibly explain a
#: price movement. Wider than news_matching's DEFAULT_DATE_WINDOW_DAYS
#: (10) on purpose: a natural event's effect on bookings/fares (an
#: airport shut for days, demand shifting before/after) plausibly
#: persists a little longer than a single news cycle.
DEFAULT_EVENT_TIME_WINDOW_DAYS = 14

WEIGHT_GEOGRAPHIC = 0.6
WEIGHT_TEMPORAL = 0.4

DEFAULT_MIN_RELEVANCE = 0.35

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in km. Standard
    haversine formula -- exact given the inputs, not fitted/estimated."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class EonetMatchingConfig:
    radius_km: float = DEFAULT_EVENT_RADIUS_KM
    time_window_days: int = DEFAULT_EVENT_TIME_WINDOW_DAYS
    min_relevance: float = DEFAULT_MIN_RELEVANCE
    top_n: int = 5

    def __post_init__(self) -> None:
        if self.radius_km <= 0:
            raise ValueError("radius_km must be positive")
        if self.time_window_days <= 0:
            raise ValueError("time_window_days must be positive")
        if not 0.0 <= self.min_relevance <= 1.0:
            raise ValueError("min_relevance must be in [0, 1]")
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def score_event(
    event: NaturalEvent,
    movement: RouteMovement,
    config: Optional[EonetMatchingConfig] = None,
) -> Optional[NaturalEventMatch]:
    """Score one real EONET event against one route's price movement.
    Returns None if neither of the route's airports has a known
    coordinate (index_engine.geo_metadata.CITY_COORDINATES) -- never
    guesses a location for scoring."""
    config = config or EonetMatchingConfig()

    origin_coord = CITY_COORDINATES.get(movement.origin.upper())
    destination_coord = CITY_COORDINATES.get(movement.destination.upper())
    if origin_coord is None and destination_coord is None:
        return None

    dist_origin = haversine_km(origin_coord[0], origin_coord[1], event.latitude, event.longitude) if origin_coord else None
    dist_dest = haversine_km(destination_coord[0], destination_coord[1], event.latitude, event.longitude) if destination_coord else None
    closest = min(d for d in (dist_origin, dist_dest) if d is not None)

    geo_score = max(0.0, 1.0 - (closest / config.radius_km)) if closest < config.radius_km else 0.0

    delta_days = abs((_as_utc(event.event_date) - _as_utc(movement.as_of)).total_seconds()) / 86400.0
    temporal_score = max(0.0, 1.0 - (delta_days / config.time_window_days)) if delta_days < config.time_window_days else 0.0

    total = WEIGHT_GEOGRAPHIC * geo_score + WEIGHT_TEMPORAL * temporal_score
    total = max(0.0, min(1.0, total))

    reasons: List[str] = []
    if geo_score > 0:
        nearer = "origin" if (dist_origin is not None and closest == dist_origin) else "destination"
        reasons.append(f"within {config.radius_km:.0f}km of {nearer} ({closest:.0f}km away)")
    if temporal_score > 0:
        reasons.append(f"within {config.time_window_days}d of the movement date ({delta_days:.1f}d away)")

    return NaturalEventMatch(
        event=event,
        route=movement.route,
        distance_from_origin_km=round(dist_origin, 1) if dist_origin is not None else None,
        distance_from_destination_km=round(dist_dest, 1) if dist_dest is not None else None,
        temporal_distance_days=delta_days,
        relevance_score=round(total, 4),
        relevance_reason=reasons,
    )


def rank_events(
    events: Iterable[NaturalEvent],
    movement: RouteMovement,
    config: Optional[EonetMatchingConfig] = None,
) -> List[NaturalEventMatch]:
    """Score every candidate event and return the top matches above
    ``config.min_relevance``, highest relevance first, ties broken by
    more recent event date. Candidates are de-duplicated by event_id
    first, same reasoning as news_matching.rank_articles's URL dedup."""
    config = config or EonetMatchingConfig()

    deduped: List[NaturalEvent] = []
    seen_ids = set()
    for e in events:
        if e.event_id in seen_ids:
            continue
        seen_ids.add(e.event_id)
        deduped.append(e)

    matches = [m for m in (score_event(e, movement, config) for e in deduped) if m is not None]
    matches = [m for m in matches if m.relevance_score >= config.min_relevance]
    matches.sort(key=lambda m: (m.relevance_score, m.event.event_date), reverse=True)
    return matches[: config.top_n]
