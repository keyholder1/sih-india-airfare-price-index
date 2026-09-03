"""Full pipeline demo against messy, scraper-shaped data.

Unlike examples/run_index.py (clean synthetic data, for quick smoke-testing),
this script deliberately injects the kind of mess a real scraper produces:
duplicate observation ids, missing optional fields, a route that only
exists in the base period (discontinued) and one that only exists in the
current period (new) — so the printed output demonstrates the quality
flags and status handling, not just the happy path.

Run from the repo root:

    python examples/integration_example.py
"""

from __future__ import annotations

import random

import pandas as pd

from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.weighting import generate_synthetic_weights

from generate_sample_fares import generate

BASE_PERIOD = "2026-01"
CURRENT_PERIOD = "2026-08"


def make_messy_batch() -> pd.DataFrame:
    df = generate()

    # 1. A route that only ever appears in the base period -> DISCONTINUED.
    df = df[~((df["origin"] == "CCU") & (df["destination"] == "DEL") & (df["flight_date"].str.startswith(("2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"))))]

    # 2. A brand-new route that only appears in the current period -> NEW_ROUTE.
    new_route_rows = []
    for i in range(25):
        row = df.iloc[i].to_dict()
        row["observation_id"] = f"NEWROUTE{i:04d}"
        row["origin"], row["destination"] = "HYD", "MAA"
        row["flight_date"] = f"2026-08-{(i % 27) + 1:02d}"
        row["booking_date"] = f"2026-07-{(i % 27) + 1:02d}"
        new_route_rows.append(row)
    df = pd.concat([df, pd.DataFrame(new_route_rows)], ignore_index=True)

    # 3. Duplicate a handful of observation_ids (scraper re-visiting the same listing).
    dup_sample = df.sample(n=10, random_state=1).copy()
    df = pd.concat([df, dup_sample], ignore_index=True)

    # 4. Null out optional fields on a chunk of rows, as a real scraper
    #    sometimes fails to extract fare_class/taxes/fees/baggage.
    optional_cols = ["fare_class", "taxes", "fees", "baggage", "duration"]
    missing_idx = df.sample(frac=0.05, random_state=2).index
    df.loc[missing_idx, optional_cols] = None

    return df.reset_index(drop=True)


def main() -> None:
    print("Simulating realistic (messy) scraper output...")
    fares = make_messy_batch()
    print(f"  {len(fares)} raw observations (includes duplicates, nulls, a discontinued route, a new route)\n")

    routes = sorted((fares["origin"] + "-" + fares["destination"]).unique())
    weights = generate_synthetic_weights(routes)
    config = IndexConfig(base_period=BASE_PERIOD, representative_method="median", outlier_method="iqr")
    engine = AirfarePriceIndex(base_period=BASE_PERIOD, weights=weights, config=config)

    result = engine.calculate(observations=fares, current_period=CURRENT_PERIOD)

    print("INDIA AIRFARE PRICE INDEX")
    print("-" * 25)
    print(f"Index: {result.national_index:.2f}")
    print(f"MoM: {result.mom_change_pct:+.2f}%" if result.mom_change_pct is not None else "MoM: n/a")
    print(f"YoY: {result.yoy_change_pct:+.2f}%" if result.yoy_change_pct is not None else "YoY: n/a (no data 12 months prior)")
    print(f"Routes covered: {result.routes_covered}/{result.routes_total}")
    print(f"Observations used: {result.observations_used}")
    print(f"Coverage: {result.coverage_rate:.1%}")

    print(f"\nData quality: received {result.observations_received}, "
          f"rejected {result.observations_rejected}, outliers flagged {result.outliers_flagged}, "
          f"routes expected {result.routes_expected}, routes with any data {result.routes_with_data}")

    contributions = [c for c in result.route_contributions if c.contribution_points is not None]
    positive = sorted((c for c in contributions if c.contribution_points > 0), key=lambda c: -c.contribution_points)
    negative = sorted((c for c in contributions if c.contribution_points < 0), key=lambda c: c.contribution_points)

    print("\nTop positive contributors:")
    for c in positive[:3]:
        print(f"  {c.route:10s} +{c.contribution_points:.3f}")
    print("Top negative contributors:")
    for c in negative[:3]:
        print(f"  {c.route:10s} {c.contribution_points:.3f}")

    print("\nRoutes needing attention (not OK):")
    for r in result.route_indices:
        if r.status != "OK":
            print(f"  {r.route:10s} status={r.status}")

    if result.quality_flags:
        print("\nQuality flags:")
        for flag in result.quality_flags:
            print(f"  - {flag}")

    print("\nJSON-serializable result available via result.to_dict() for the backend team.")


if __name__ == "__main__":
    main()
