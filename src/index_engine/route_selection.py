"""Scraper route-coverage planning: which additional routes give the most
passenger-traffic coverage per route added.

This module does NOT touch the price index, weighting, or any other
statistical calculation — it only ranks and tiers the real DGCA route
universe (already loaded by index_engine.traffic) to answer a planning
question: "what should the scraper cover next?" Everything here operates
on DGCA city names; converting a specific chosen route into engine-ready
IATA-coded weights is still traffic.to_engine_weights()'s job.

Passenger traffic here is used as a route-IMPORTANCE measure for THIS
airfare index, not an official CPI representativeness measure — see
docs/methodology.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

TIER_LABELS = {
    1: "TIER 1 - Essential",
    2: "TIER 2 - High value",
    3: "TIER 3 - Expansion",
    4: "TIER 4 - Long tail",
}


def rank_routes_by_traffic(national_weights_df: pd.DataFrame) -> pd.DataFrame:
    """Sort routes by national_weight descending and attach rank + cumulative
    coverage columns. Input must already have an origin/destination/
    national_weight column, e.g. the output of traffic.national_weights()."""
    ranked = national_weights_df.sort_values("national_weight", ascending=False).reset_index(drop=True)
    ranked["rank"] = ranked.index + 1
    ranked["cumulative_coverage"] = ranked["national_weight"].cumsum()
    return ranked


def coverage_at_n(ranked_df: pd.DataFrame, n: int) -> float:
    """Traffic coverage achieved by the top n ranked routes."""
    if n <= 0:
        return 0.0
    return float(ranked_df.head(n)["national_weight"].sum())


def find_routes_for_target_coverage(ranked_df: pd.DataFrame, target: float) -> Optional[int]:
    """Minimum number of top-ranked routes needed to reach ``target``
    coverage (e.g. 0.5 for 50%). Returns None if the full route universe
    still falls short (should not happen with a real 0-1 target and a
    complete ranked_df, but handled rather than assumed)."""
    if target <= 0:
        return 0
    reached = ranked_df[ranked_df["cumulative_coverage"] >= target]
    if reached.empty:
        return None
    return int(reached.iloc[0]["rank"])


def coverage_scenarios(ranked_df: pd.DataFrame, route_counts: List[int]) -> pd.DataFrame:
    """Routes | Traffic Coverage | Incremental Gain table for the given
    list of route-count checkpoints (e.g. [10, 20, 30, 50, 75, 100, 150])."""
    rows = []
    previous_coverage = 0.0
    for n in sorted(route_counts):
        coverage = coverage_at_n(ranked_df, n)
        rows.append({"routes": n, "traffic_coverage": coverage, "incremental_gain": coverage - previous_coverage})
        previous_coverage = coverage
    return pd.DataFrame(rows)


def target_coverage_table(ranked_df: pd.DataFrame, targets: List[float]) -> pd.DataFrame:
    rows = [{"target_coverage": t, "minimum_routes": find_routes_for_target_coverage(ranked_df, t)} for t in targets]
    return pd.DataFrame(rows)


def bidirectional_summary(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """City-pair summary combining both directions, for SCRAPER PRIORITIZATION
    ONLY — never used to replace the directional weights the price index
    actually consumes (airfares are directional; this table is not)."""
    working = ranked_df.copy()
    working["city_pair"] = working.apply(lambda r: " <-> ".join(sorted([r["origin"], r["destination"]])), axis=1)
    grouped = (
        working.groupby("city_pair", as_index=False)
        .agg(passengers=("passengers", "sum"), national_weight=("national_weight", "sum"))
        .sort_values("national_weight", ascending=False)
        .reset_index(drop=True)
    )
    grouped["rank"] = grouped.index + 1
    return grouped


def assign_tiers(ranked_df: pd.DataFrame, tier_cutoffs: Tuple[int, int, int] = (20, 50, 100)) -> pd.DataFrame:
    """Tier boundaries are rank cutoffs, chosen from where marginal coverage
    gain per route visibly drops off (see docs/methodology.md "Route
    Coverage Expansion" for the actual numbers behind the default 20/50/100
    cutoffs) — not arbitrary round numbers."""
    tier1_end, tier2_end, tier3_end = tier_cutoffs
    result = ranked_df.copy()

    def tier_for(rank: int) -> int:
        if rank <= tier1_end:
            return 1
        if rank <= tier2_end:
            return 2
        if rank <= tier3_end:
            return 3
        return 4

    result["tier"] = result["rank"].apply(tier_for)
    result["tier_label"] = result["tier"].map(TIER_LABELS)
    return result


def mark_currently_covered(ranked_df: pd.DataFrame, covered_city_routes: List[Tuple[str, str]]) -> pd.DataFrame:
    covered_set = set(covered_city_routes)
    result = ranked_df.copy()
    result["currently_covered"] = result.apply(lambda r: (r["origin"], r["destination"]) in covered_set, axis=1)
    return result


def city_level_traffic(long_df_or_ranked: pd.DataFrame) -> pd.DataFrame:
    """Total traffic per city across ALL its routes (origin + destination
    sides combined) — used for geographic representativeness, not for
    route weighting itself."""
    outgoing = long_df_or_ranked.groupby("origin", as_index=False)["passengers"].sum().rename(columns={"origin": "city"})
    incoming = long_df_or_ranked.groupby("destination", as_index=False)["passengers"].sum().rename(columns={"destination": "city"})
    combined = pd.concat([outgoing, incoming]).groupby("city", as_index=False)["passengers"].sum()
    combined = combined.sort_values("passengers", ascending=False).reset_index(drop=True)
    combined["rank"] = combined.index + 1
    return combined


def underrepresented_cities(city_traffic: pd.DataFrame, top_route_cities: set, top_n_cities: int = 30) -> pd.DataFrame:
    """Cities that rank highly by total node-level traffic but have none of
    their routes in the chosen top-route set — a real gap a pure
    route-level ranking can hide (a city's traffic can be spread thin
    across many routes, none individually cracking the top N)."""
    top_cities = city_traffic.head(top_n_cities)
    return top_cities[~top_cities["city"].isin(top_route_cities)].reset_index(drop=True)
