"""Route input — reads ``data/routes/recommended_routes.json`` (produced by
the route-coverage-expansion analysis, see docs/methodology.md) rather than
hard-coding any route list in this package.

Deliberately does not import anything from ``index_engine`` — this file is
pure I/O + filtering, no statistical meaning attached to a route here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .config import DEFAULT_ROUTES_PATH


@dataclass
class RouteSpec:
    """One route to collect fares for, as described by the route file —
    not a statistical object, just "what to ask sources for"."""

    origin: str
    destination: str
    origin_city: str
    destination_city: str
    tier: int
    priority: int
    national_weight: Optional[float]
    currently_covered: bool

    @property
    def route(self) -> str:
        return f"{self.origin}-{self.destination}"

    def to_dict(self) -> dict:
        return asdict(self)


def load_routes(
    path: str = DEFAULT_ROUTES_PATH,
    tiers: Optional[Iterable[int]] = None,
    repo_root: Optional[Path] = None,
) -> List[RouteSpec]:
    """Load routes from the recommended-routes file, optionally filtered to
    a subset of tiers (e.g. ``tiers=(1,)`` for Tier 1 only).

    ``repo_root`` lets callers/tests point at a repo checked out somewhere
    other than the current working directory; defaults to resolving
    ``path`` relative to cwd (the same convention every other example
    script in this repo uses).
    """
    full_path = (repo_root / path) if repo_root is not None else Path(path)
    with open(full_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    tier_filter = set(tiers) if tiers is not None else None
    routes = []
    for row in payload["routes"]:
        if tier_filter is not None and row["tier"] not in tier_filter:
            continue
        # Some rows have a null origin_iata/destination_iata by design --
        # city_mapping.py documents this for cities deliberately excluded
        # from IATA mapping (e.g. the "MUMBAI (MUMBAI)" duplicate-city
        # entry, kept separate from the real "MUMBAI"/BOM row to avoid
        # double-counting). Without this guard, load_routes(tiers=(1,))
        # (the scraper's own default) hands the runner a route whose
        # origin AND destination are both None -- every source then gets
        # asked to search a nonsensical "None-None" route, and the run
        # report counts it as a "successfully collected" route even
        # though every resulting observation is later rejected by
        # data_quality/index_engine validation as MISSING_REQUIRED_FIELD.
        # Skipping it here means the scraper never asks a source for a
        # route that cannot exist, instead of relying on downstream
        # validation to quietly clean up after it.
        if not row.get("origin_iata") or not row.get("destination_iata"):
            continue
        routes.append(
            RouteSpec(
                origin=row["origin_iata"],
                destination=row["destination_iata"],
                origin_city=row["origin_city"],
                destination_city=row["destination_city"],
                tier=row["tier"],
                priority=row["priority"],
                national_weight=row.get("national_weight"),
                currently_covered=row.get("currently_covered", False),
            )
        )
    return sorted(routes, key=lambda r: r.priority)


def route_pairs(routes: Iterable[RouteSpec]) -> List[Tuple[str, str]]:
    """Convenience: ``[(origin, destination), ...]`` for callers that just
    want the pairs, e.g. to hand to a source's ``search_fares``."""
    return [(r.origin, r.destination) for r in routes]
