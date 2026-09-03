"""Route-level inflation analysis: WHERE airfare inflation is happening,
and whether it actually matters to the national number.

Built entirely on top of things the engine already computes
(``IndexResult.route_indices``, ``route_contributions``) plus optional
volatility and DGCA traffic-weight inputs — this module does not
reimplement or duplicate the price-index or contribution formulas.

Central point (see docs/methodology.md): high inflation on a route and
high importance to the national index are NOT the same thing. A route can
move +12% and matter very little; another can move +3% and dominate the
national figure. ``RouteInflationRow`` always carries inflation, traffic
weight, and contribution together so a consumer never sees one without
the others.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Literal, Optional

import pandas as pd

from .geo_metadata import CITY_COORDINATES
from .models import IndexResult, RouteContribution


@dataclass
class RouteInflationRow:
    route: str
    origin: str
    destination: str
    current_index: Optional[float]
    mom_inflation_pct: Optional[float]
    yoy_inflation_pct: Optional[float]
    weight: Optional[float]
    traffic_weight: Optional[float]
    contribution: Optional[float]
    volatility: Optional[float]
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def build_route_inflation_table(
    current: IndexResult,
    prev_month: IndexResult,
    prev_year: IndexResult,
    contributions: List[RouteContribution],
    volatility_by_route: Optional[Dict[str, float]] = None,
    traffic_weight_by_route: Optional[Dict[str, float]] = None,
) -> List[RouteInflationRow]:
    prev_month_by_route = {r.route: r for r in prev_month.route_indices}
    prev_year_by_route = {r.route: r for r in prev_year.route_indices}
    contribution_by_route = {c.route: c for c in contributions}
    volatility_by_route = volatility_by_route or {}
    traffic_weight_by_route = traffic_weight_by_route or {}

    rows = []
    for cur in current.route_indices:
        pm = prev_month_by_route.get(cur.route)
        py = prev_year_by_route.get(cur.route)

        mom = _pct_change(cur.route_index, pm.route_index) if cur.status == "OK" and pm and pm.status == "OK" else None
        yoy = _pct_change(cur.route_index, py.route_index) if cur.status == "OK" and py and py.status == "OK" else None
        contrib = contribution_by_route.get(cur.route)

        rows.append(
            RouteInflationRow(
                route=cur.route,
                origin=cur.origin,
                destination=cur.destination,
                current_index=cur.route_index,
                mom_inflation_pct=mom,
                yoy_inflation_pct=yoy,
                weight=cur.weight_normalized,
                traffic_weight=traffic_weight_by_route.get(cur.route),
                contribution=contrib.contribution_points if contrib else None,
                volatility=volatility_by_route.get(cur.route),
                status=cur.status,
            )
        )
    return rows


def inflation_matrix(rows: List[RouteInflationRow], metric: Literal["mom", "yoy"] = "mom") -> pd.DataFrame:
    """Origin x Destination matrix of inflation %. Missing routes are NaN
    (pandas default for an unset cell), never 0 — a route with no data is
    not a route with zero inflation."""
    origins = sorted({r.origin for r in rows})
    destinations = sorted({r.destination for r in rows})
    matrix = pd.DataFrame(index=origins, columns=destinations, dtype=float)
    for r in rows:
        value = r.mom_inflation_pct if metric == "mom" else r.yoy_inflation_pct
        if value is not None:
            matrix.loc[r.origin, r.destination] = value
    return matrix


def route_map_objects(rows: List[RouteInflationRow]) -> List[dict]:
    """Frontend-ready route objects with geographic coordinates attached.
    Routes with an unmapped city (no entry in geo_metadata) are skipped."""
    objects = []
    for r in rows:
        origin_coord = CITY_COORDINATES.get(r.origin)
        destination_coord = CITY_COORDINATES.get(r.destination)
        if origin_coord is None or destination_coord is None:
            continue
        objects.append(
            {
                "origin": r.origin,
                "destination": r.destination,
                "origin_lat": origin_coord[0],
                "origin_lon": origin_coord[1],
                "destination_lat": destination_coord[0],
                "destination_lon": destination_coord[1],
                "inflation_mom": r.mom_inflation_pct,
                "inflation_yoy": r.yoy_inflation_pct,
                "volatility": r.volatility,
                "traffic_weight": r.traffic_weight,
                "contribution": r.contribution,
                "status": r.status,
            }
        )
    return objects


def top_rankings(rows: List[RouteInflationRow], top_n: int = 5) -> Dict[str, List[RouteInflationRow]]:
    by_mom = [r for r in rows if r.mom_inflation_pct is not None]
    by_yoy = [r for r in rows if r.yoy_inflation_pct is not None]
    by_contribution = [r for r in rows if r.contribution is not None]
    by_traffic = [r for r in rows if r.traffic_weight is not None]
    by_volatility = [r for r in rows if r.volatility is not None]

    return {
        "highest_mom_inflation": sorted(by_mom, key=lambda r: -r.mom_inflation_pct)[:top_n],
        "lowest_mom_inflation": sorted(by_mom, key=lambda r: r.mom_inflation_pct)[:top_n],
        "highest_yoy_inflation": sorted(by_yoy, key=lambda r: -r.yoy_inflation_pct)[:top_n],
        "lowest_yoy_inflation": sorted(by_yoy, key=lambda r: r.yoy_inflation_pct)[:top_n],
        "largest_positive_contributors": sorted(by_contribution, key=lambda r: -r.contribution)[:top_n],
        "largest_negative_contributors": sorted(by_contribution, key=lambda r: r.contribution)[:top_n],
        "highest_traffic_weight": sorted(by_traffic, key=lambda r: -r.traffic_weight)[:top_n],
        "highest_volatility": sorted(by_volatility, key=lambda r: -r.volatility)[:top_n],
    }
