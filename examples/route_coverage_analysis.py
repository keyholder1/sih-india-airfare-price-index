"""Route-coverage expansion analysis: which additional routes give the
scraper team the most passenger-traffic coverage per route added.

Uses ONLY the real, already-committed DGCA dataset — no fabricated
numbers. Produces:
  - printed tables (coverage scenarios, target-coverage lookup, top routes,
    tiers, geographic gaps)
  - data/routes/scraper_route_priority.csv (full ranked+tiered table)
  - data/routes/recommended_routes.json (machine-readable, for the scraper team)
  - examples/route_coverage_curve.png (coverage vs. route count chart)
  - a sensitivity comparison: current 10 routes vs. Tier 1 vs. Tier 1+2,
    using SYNTHETIC fares extended to the recommended routes (no real fare
    data exists yet for routes beyond the original 10 — this comparison is
    about traffic-weight coverage and mechanics, not real fare inflation
    for the new routes)

Run from the repo root:

    python examples/route_coverage_analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.city_mapping import CITY_TO_IATA, city_to_iata, iata_to_city
from index_engine.route_selection import (
    assign_tiers,
    bidirectional_summary,
    city_level_traffic,
    coverage_scenarios,
    mark_currently_covered,
    rank_routes_by_traffic,
    target_coverage_table,
    underrepresented_cities,
)
from index_engine.traffic import aggregate_period, latest_available_period, load_dgca_traffic, national_weights, rolling_window, to_directional, validate_traffic

from generate_sample_fares import generate

DGCA_CSV = Path(__file__).parent.parent / "data" / "traffic" / "dgca_domestic_city_pairs.csv"
DATA_ROUTES_DIR = Path(__file__).parent.parent / "data" / "routes"
BASE_PERIOD = "2026-01"
CURRENT_PERIOD = "2026-08"

CURRENT_ROUTES_IATA = [
    ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
    ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
    ("CCU", "DEL"), ("BLR", "BOM"),
]
TIER_CUTOFFS = (20, 50, 100)  # see docs/methodology.md "Route Coverage Expansion" for why


def load_ranked_routes() -> pd.DataFrame:
    raw = load_dgca_traffic(str(DGCA_CSV))
    valid, _ = validate_traffic(raw)
    long_df = to_directional(valid, source="DGCA")
    end = latest_available_period(long_df)
    start, end = rolling_window(end, 12)
    agg = aggregate_period(long_df, start, end)
    nat = national_weights(agg)
    ranked = rank_routes_by_traffic(nat)
    return ranked, start, end


def mappable_iata_route(origin_city: str, destination_city: str):
    """Only cities we've verified in index_engine.city_mapping can be
    converted to IATA — anything else is left as a city-name-only row
    rather than guessed."""
    try:
        return city_to_iata(origin_city), city_to_iata(destination_city)
    except KeyError:
        return None


def main() -> None:
    DATA_ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    ranked, window_start, window_end = load_ranked_routes()
    current_city_routes = [(iata_to_city(o), iata_to_city(d)) for o, d in CURRENT_ROUTES_IATA]

    ranked = mark_currently_covered(ranked, current_city_routes)
    ranked = assign_tiers(ranked, tier_cutoffs=TIER_CUTOFFS)

    print("=" * 78)
    print(f"DGCA ROUTE COVERAGE ANALYSIS  (window: {window_start} to {window_end}, real data)")
    print("=" * 78)
    print(f"Total DGCA directional routes in window: {len(ranked)}")
    print(f"Current airfare-index route universe: {len(CURRENT_ROUTES_IATA)} routes, "
          f"{ranked.head(len(ranked))[ranked['currently_covered']]['national_weight'].sum():.2%} traffic coverage")

    print("\nTop 30 routes by real passenger traffic:")
    print(ranked.head(30)[["rank", "origin", "destination", "passengers", "national_weight", "cumulative_coverage", "currently_covered", "tier"]].to_string(index=False))

    print("\nCoverage scenarios (Step 4):")
    scenarios = coverage_scenarios(ranked, [10, 20, 30, 50, 75, 100, 150, 200, 300, 500])
    print(scenarios.to_string(index=False, formatters={"traffic_coverage": "{:.1%}".format, "incremental_gain": "{:+.1%}".format}))

    print("\nMinimum routes needed for target coverage (Step 5):")
    targets = target_coverage_table(ranked, [0.25, 0.5, 0.6, 0.7, 0.8, 0.9])
    print(targets.to_string(index=False, formatters={"target_coverage": "{:.0%}".format}))

    print("\nBidirectional city-pair summary, top 10 (prioritization only, Step 7):")
    bidi = bidirectional_summary(ranked)
    print(bidi.head(10)[["rank", "city_pair", "passengers", "national_weight"]].to_string(index=False))

    print("\nGeographic representativeness (Step 10):")
    city_traffic = city_level_traffic(ranked)
    top_route_cities = set(ranked.head(TIER_CUTOFFS[2])["origin"]) | set(ranked.head(TIER_CUTOFFS[2])["destination"])
    gaps = underrepresented_cities(city_traffic, top_route_cities, top_n_cities=30)
    if gaps.empty:
        print(f"  No gaps: every one of the top-30 cities by total node traffic has at least one route in the top {TIER_CUTOFFS[2]}.")
    else:
        print(f"  Cities with high total traffic but no route in the top {TIER_CUTOFFS[2]} routes:")
        print(gaps.to_string(index=False))

    # --- Write data files (Step 11, 12) ---
    top_n_for_file = 150
    priority_table = ranked.head(top_n_for_file).copy()
    priority_table["city_pair"] = priority_table["origin"] + " <-> " + priority_table["destination"]
    priority_table["priority_rank"] = priority_table["rank"]
    priority_table["recommended"] = priority_table["tier"] <= 3
    priority_table["geographic_reason"] = priority_table.apply(
        lambda r: "core metro trunk route" if r["origin"] in ("DELHI", "MUMBAI", "BENGALURU") and r["destination"] in ("DELHI", "MUMBAI", "BENGALURU") else "high-traffic route", axis=1
    )
    priority_table["source"] = "DGCA_DERIVED_ROUTE_PRIORITY"
    csv_path = DATA_ROUTES_DIR / "scraper_route_priority.csv"
    priority_table[[
        "priority_rank", "tier", "tier_label", "origin", "destination", "city_pair", "passengers",
        "national_weight", "cumulative_coverage", "currently_covered", "recommended", "geographic_reason", "source",
    ]].to_csv(csv_path, index=False)
    print(f"\nWrote {csv_path} ({len(priority_table)} routes)")

    recommended_routes = []
    for _, row in ranked.head(TIER_CUTOFFS[2]).iterrows():
        mapped = mappable_iata_route(row["origin"], row["destination"])
        recommended_routes.append(
            {
                "origin_city": row["origin"],
                "destination_city": row["destination"],
                "origin_iata": mapped[0] if mapped else None,
                "destination_iata": mapped[1] if mapped else None,
                "priority": int(row["rank"]),
                "tier": int(row["tier"]),
                "national_weight": row["national_weight"],
                "currently_covered": bool(row["currently_covered"]),
            }
        )
    recommended_json = {
        "source": "DGCA-derived passenger traffic (route-importance weights, NOT official CPI weights)",
        "weight_period": f"{window_start} to {window_end}",
        "tier_cutoffs": {"tier_1_end_rank": TIER_CUTOFFS[0], "tier_2_end_rank": TIER_CUTOFFS[1], "tier_3_end_rank": TIER_CUTOFFS[2]},
        "routes": recommended_routes,
    }
    json_path = DATA_ROUTES_DIR / "recommended_routes.json"
    json_path.write_text(json.dumps(recommended_json, indent=2))
    print(f"Wrote {json_path} ({len(recommended_routes)} routes)")

    # --- Coverage curve chart (Step 14) ---
    fig, ax = plt.subplots(figsize=(9, 5))
    curve_points = list(range(1, min(500, len(ranked)) + 1))
    coverage_curve = ranked["cumulative_coverage"].iloc[:len(curve_points)].to_numpy()
    ax.plot(curve_points, coverage_curve * 100)
    for n in [10, 20, 50, 100, 150]:
        ax.axvline(n, color="grey", linestyle=":", linewidth=0.8)
    ax.axvline(len(CURRENT_ROUTES_IATA), color="red", linestyle="--", label="Current (10 routes)")
    ax.set_xlabel("Number of routes (traffic-priority order)")
    ax.set_ylabel("Cumulative traffic coverage (%)")
    ax.set_title("DGCA Passenger-Traffic Coverage vs. Route Count (real data)")
    ax.legend()
    fig.tight_layout()
    chart_path = Path(__file__).parent / "route_coverage_curve.png"
    fig.savefig(chart_path, dpi=150)
    print(f"Saved {chart_path}")

    # --- Step 17: sensitivity comparison across route universes ---
    print("\n" + "=" * 78)
    print("SENSITIVITY: index results under current vs. expanded route universes")
    print("=" * 78)

    tier1_city_routes = list(zip(ranked.head(TIER_CUTOFFS[0])["origin"], ranked.head(TIER_CUTOFFS[0])["destination"]))
    tier12_city_routes = list(zip(ranked.head(TIER_CUTOFFS[1])["origin"], ranked.head(TIER_CUTOFFS[1])["destination"]))

    def to_iata_universe(city_routes):
        mapped = [mappable_iata_route(o, d) for o, d in city_routes]
        return [pair for pair in mapped if pair is not None]

    scenarios_to_run = {
        "Current (10 routes)": to_iata_universe(current_city_routes),
        f"Tier 1 (top {TIER_CUTOFFS[0]} routes)": to_iata_universe(tier1_city_routes),
        f"Tier 1+2 (top {TIER_CUTOFFS[1]} routes)": to_iata_universe(tier12_city_routes),
    }

    for label, (city_routes, iata_routes) in {
        "Current (10 routes)": (current_city_routes, scenarios_to_run["Current (10 routes)"]),
        f"Tier 1 (top {TIER_CUTOFFS[0]} routes)": (tier1_city_routes, scenarios_to_run[f"Tier 1 (top {TIER_CUTOFFS[0]} routes)"]),
        f"Tier 1+2 (top {TIER_CUTOFFS[1]} routes)": (tier12_city_routes, scenarios_to_run[f"Tier 1+2 (top {TIER_CUTOFFS[1]} routes)"]),
    }.items():
        skipped = len(city_routes) - len(iata_routes)
        if skipped:
            print(f"  ({label}: {skipped} route(s) skipped, no verified IATA mapping yet - e.g. a MUMBAI (MUMBAI) variant)")
        if len(iata_routes) < 2:
            print(f"{label}: too few IATA-mappable routes to run ({len(iata_routes)}) — mapping needs extending")
            continue
        fares = generate(routes=iata_routes)
        city_routes_for_weights = [(iata_to_city(o), iata_to_city(d)) for o, d in iata_routes]
        ranked_subset = ranked[ranked.apply(lambda r: (r["origin"], r["destination"]) in set(city_routes_for_weights), axis=1)]
        coverage = ranked_subset["national_weight"].sum()

        weights_rows = []
        total_w = ranked_subset["national_weight"].sum()
        for _, row in ranked_subset.iterrows():
            o_iata, d_iata = city_to_iata(row["origin"]), city_to_iata(row["destination"])
            weights_rows.append({"origin": o_iata, "destination": d_iata, "weight": row["national_weight"] / total_w if total_w else 0, "source": "DGCA_DERIVED"})
        weights_df = pd.DataFrame(weights_rows)

        config = IndexConfig(base_period=BASE_PERIOD, representative_method="median", outlier_method="iqr")
        engine = AirfarePriceIndex(base_period=BASE_PERIOD, weights=weights_df, config=config)
        result = engine.calculate(fares, current_period=CURRENT_PERIOD)

        mom = f"{result.mom_change_pct:+.2f}%" if result.mom_change_pct is not None else "n/a"
        yoy = f"{result.yoy_change_pct:+.2f}%" if result.yoy_change_pct is not None else "n/a"
        print(f"{label:28s} routes={len(iata_routes):3d}  index={result.national_index:6.2f}  MoM={mom:>8s}  YoY={yoy:>8s}  traffic_coverage={coverage:.1%}")


if __name__ == "__main__":
    main()
