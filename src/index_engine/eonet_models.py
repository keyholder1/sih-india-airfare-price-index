"""Typed data structures for the NASA EONET natural-event context layer.

Mirrors news_models.py's style exactly: plain dataclasses with a
to_dict(), no framework dependency. Nothing here is imported by
index.py, aggregation.py, or any module that computes the price index,
and nothing here mutates an IndexResult, a RouteInflationRow, or any
other index output -- it only reads a route's already-computed movement.
See docs/eonet_context.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

#: EONET's own category vocabulary -- https://eonet.gsfc.nasa.gov/api/v3/categories,
#: verified live 2026-09-04. Listed here for reference/validation only;
#: eonet_context.py's RELEVANT_CATEGORIES is the deliberate subset this
#: project actually queries for.
EONET_CATEGORIES = (
    "drought",
    "dustHaze",
    "earthquakes",
    "floods",
    "landslides",
    "manmade",
    "seaLakeIce",
    "severeStorms",
    "snow",
    "tempExtremes",
    "volcanoes",
    "waterColor",
    "wildfires",
)


@dataclass
class NaturalEvent:
    """One real EONET event. ``is_mock`` mirrors NewsArticle's own
    convention (news_models.py) -- True only for MockEonetClient's
    explicitly-fabricated demo fixtures, never for anything parsed from
    a real EONET response."""

    event_id: str
    title: str
    category: str
    category_label: str
    event_date: datetime
    latitude: float
    longitude: float
    is_closed: bool
    magnitude_value: Optional[float] = None
    magnitude_unit: Optional[str] = None
    source_url: Optional[str] = None
    description: Optional[str] = None
    is_mock: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_date"] = self.event_date.isoformat()
        return d

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], category_labels: Dict[str, str]) -> Optional["NaturalEvent"]:
        """Parses one raw EONET /events JSON object into a NaturalEvent.
        Returns None (never guesses/fabricates) when the event can't be
        safely parsed:

        - no ``Point``-type geometry entry. EONET events also use
          ``Polygon`` geometry (observed live for flood events) whose
          coordinate axis order could not be confirmed against this
          project's [lat, lon] convention with confidence -- rather than
          risk silently swapping latitude/longitude for those events,
          they are excluded from matching entirely. This is a stated,
          documented limitation (see docs/eonet_context.md), not a
          silent bug: only Point-geometry events (confirmed live to use
          standard GeoJSON [lon, lat] ordering) are matched.
        - missing id/title/category/date/coordinates.
        """
        try:
            event_id = raw["id"]
            title = raw["title"]
        except (KeyError, TypeError):
            return None
        if not event_id or not title:
            return None

        categories = raw.get("categories") or []
        if not categories or not isinstance(categories, list):
            return None
        category = categories[0].get("id")
        if not category:
            return None

        geometry = raw.get("geometry") or []
        if not isinstance(geometry, list) or not geometry:
            return None
        # Latest geometry entry -- for an event tracked over time (e.g. a
        # storm's path), this is its most recently recorded position/date.
        point = next((g for g in reversed(geometry) if g.get("type") == "Point"), None)
        if point is None:
            return None  # Polygon-only event -- see docstring above.

        coords = point.get("coordinates")
        if not isinstance(coords, list) or len(coords) != 2:
            return None
        lon, lat = coords  # GeoJSON order, verified live for Point geometry
        raw_date = point.get("date")
        if not raw_date:
            return None
        try:
            event_date = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

        sources = raw.get("sources") or []
        source_url = sources[0].get("url") if sources and isinstance(sources, list) else None
        source_url = source_url or raw.get("link")

        return cls(
            event_id=str(event_id),
            title=str(title),
            category=category,
            category_label=category_labels.get(category, category),
            event_date=event_date,
            latitude=float(lat),
            longitude=float(lon),
            is_closed=raw.get("closed") is not None,
            magnitude_value=point.get("magnitudeValue"),
            magnitude_unit=point.get("magnitudeUnit"),
            source_url=source_url,
            description=raw.get("description"),
            is_mock=False,
        )


@dataclass
class NaturalEventMatch:
    """One NaturalEvent matched to a route's price movement, with the
    score and the reasons it matched -- mirrors NewsMatch (news_models.py)."""

    event: NaturalEvent
    route: str
    distance_from_origin_km: Optional[float]
    distance_from_destination_km: Optional[float]
    temporal_distance_days: float
    relevance_score: float
    relevance_reason: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event": self.event.to_dict(),
            "route": self.route,
            "distance_from_origin_km": self.distance_from_origin_km,
            "distance_from_destination_km": self.distance_from_destination_km,
            "temporal_distance_days": round(self.temporal_distance_days, 2),
            "relevance_score": self.relevance_score,
            "relevance_reason": self.relevance_reason,
        }
