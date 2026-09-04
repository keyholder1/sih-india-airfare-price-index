"""EONET Natural Event context layer -- answers "was there a real
natural event near this route, around this time, that provides context
for its fare movement?" Strictly downstream of the price index, exactly
like news_context.py:

    AirfarePriceIndex -> route price movement -> significant movement?
        -> EONET Context layer -> nearby/recent real events -> dashboard

Optional and additive. Nothing here is imported by index.py or
aggregation.py, and nothing here mutates an IndexResult, a
RouteInflationRow, or any other index output -- it only reads them.
RouteMovement, is_significant_movement and route_movement_from_row are
imported from news_context.py / news_models.py rather than redefined
here -- the concept ("a route's already-computed price movement, and
whether it's worth explaining") is identical for news and for natural
events; only the source of candidate explanations differs.

See docs/eonet_context.md for the full write-up, including why this
never claims causality (same CAUSATION_DISCLAIMER as the news layer)
and exactly what happens when EONET is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .eonet_client import EonetClient, EonetFetchResult
from .eonet_matching import EonetMatchingConfig, rank_events
from .eonet_models import NaturalEvent, NaturalEventMatch
from .news_models import CAUSATION_DISCLAIMER, RouteMovement  # reused, not duplicated

#: India bounding box (minLon, minLat, maxLon, maxLat) -- narrows the
#: EONET query server-side to events plausibly relevant to any Indian
#: domestic route, rather than fetching every event on Earth. Generous
#: on purpose (includes neighbouring-country events near the border,
#: e.g. a cyclone that formed over the Bay of Bengal before landfall) --
#: precise per-route relevance is still decided by eonet_matching's real
#: distance calculation, not by this bounding box. Verified live
#: (2026-09-04) to return real India-region events.
INDIA_BBOX = "68,6,98,37"

#: How far back to look for events -- EONET's own `days` query
#: parameter. Wider than eonet_matching.DEFAULT_EVENT_TIME_WINDOW_DAYS on
#: purpose: this bounds what's *fetched* (the candidate pool); matching
#: separately bounds what's *scored as relevant* to one specific
#: movement. A 90-day fetch window with a 14-day match window means a
#: route movement anywhere in the last ~76 days can still find a
#: temporally-close event without re-fetching.
DEFAULT_LOOKBACK_DAYS = 90

#: EONET categories mapped into this project -- a deliberate subset of
#: EONET's own 13 (eonet_models.EONET_CATEGORIES, verified live
#: 2026-09-04), chosen for plausible relevance to airline
#: operations/demand. Every id here is a real EONET category id, never
#: invented. Excluded: seaLakeIce, waterColor (no plausible link to
#: Indian domestic air travel), manmade (too broad/ambiguous to score
#: meaningfully as a single category), drought, landslides, snow (not
#: typically flight-operationally relevant the way a storm, wildfire
#: smoke, volcanic ash, or extreme heat/cold is). floods is included
#: despite most flood events using Polygon geometry this project
#: doesn't match (see eonet_models.NaturalEvent.from_raw) -- harmless to
#: request; any flood event that does carry a Point geometry is still
#: usable.
RELEVANT_CATEGORIES = (
    "severeStorms",
    "wildfires",
    "volcanoes",
    "floods",
    "tempExtremes",
    "dustHaze",
    "earthquakes",
)

CATEGORY_LABELS = {
    "severeStorms": "Severe Storm",
    "wildfires": "Wildfire",
    "volcanoes": "Volcanic Activity",
    "floods": "Flood",
    "tempExtremes": "Extreme Temperature",
    "dustHaze": "Dust / Haze",
    "earthquakes": "Earthquake",
}

CATEGORY_EMOJI = {
    "severeStorms": "\U0001f327️",
    "wildfires": "\U0001f525",
    "volcanoes": "\U0001f30b",
    "floods": "\U0001f30a",
    "tempExtremes": "\U0001f321️",
    "dustHaze": "\U0001f32b️",
    "earthquakes": "\U0001f3da️",
}


@dataclass
class EonetContextResult:
    """Full output of matching real EONET events to one route's price
    movement. ``status`` is "UNAVAILABLE" (never a fabricated empty
    "OK") when the underlying EONET fetch itself failed -- see
    docs/eonet_context.md "Failure isolation"."""

    movement: RouteMovement
    matches: List[NaturalEventMatch]
    status: str  # "OK" | "UNAVAILABLE"
    error_detail: Optional[str] = None
    disclaimer: str = CAUSATION_DISCLAIMER

    def to_dict(self) -> dict:
        return {
            "movement": self.movement.to_dict(),
            "matches": [m.to_dict() for m in self.matches],
            "status": self.status,
            "error_detail": self.error_detail,
            "disclaimer": self.disclaimer,
        }


class EonetContextService:
    """Wires an EonetClient + matching config together. Never raises --
    an EONET failure degrades this service's own result to
    status="UNAVAILABLE"; it must never propagate up and break the
    index/analytics/dashboard.
    """

    def __init__(self, client: Optional[EonetClient] = None, matching_config: Optional[EonetMatchingConfig] = None) -> None:
        self.client = client or EonetClient()
        self.matching_config = matching_config or EonetMatchingConfig()

    def _fetch_relevant_events(self) -> EonetFetchResult:
        # One request across every category of interest, India-wide --
        # cheaper and simpler than one call per category, and the client
        # itself caches this per unique parameter set.
        try:
            return self.client.get_events(
                category=",".join(RELEVANT_CATEGORIES),
                bbox=INDIA_BBOX,
                days=DEFAULT_LOOKBACK_DAYS,
                status="all",
            )
        except Exception as exc:  # noqa: BLE001 -- EONET must never take the pipeline down with it
            return EonetFetchResult(status="UNAVAILABLE", error_detail=f"{type(exc).__name__}: {exc}")

    def get_context(self, movement: RouteMovement) -> EonetContextResult:
        fetch = self._fetch_relevant_events()
        if fetch.status != "SUCCESS":
            return EonetContextResult(movement=movement, matches=[], status="UNAVAILABLE", error_detail=fetch.error_detail)

        events: List[NaturalEvent] = []
        for raw in fetch.events:
            parsed = NaturalEvent.from_raw(raw, CATEGORY_LABELS)
            if parsed is not None:
                events.append(parsed)

        matches = rank_events(events, movement, self.matching_config)
        return EonetContextResult(movement=movement, matches=matches, status="OK")
