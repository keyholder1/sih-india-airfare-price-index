"""End-to-end demo: generate synthetic fares, compute the index, print results.

Run from the repo root:

    python examples/run_index.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.weighting import generate_synthetic_weights

from generate_sample_fares import generate

BASE_PERIOD = "2026-01"
CURRENT_PERIOD = "2026-08"


def main() -> None:
    print("Generating SYNTHETIC DEMONSTRATION DATA (not real market prices)...")
    fares = generate()
    fares.to_csv(Path(__file__).parent / "sample_fares.csv", index=False)
    routes = sorted((fares["origin"] + "-" + fares["destination"]).unique())
    print(f"  {len(fares)} synthetic observations across {len(routes)} routes\n")

    weights = generate_synthetic_weights(routes)
    weights.to_csv(Path(__file__).parent / "sample_weights.csv", index=False)

    config = IndexConfig(base_period=BASE_PERIOD, representative_method="median", outlier_method="iqr")
    engine = AirfarePriceIndex(base_period=BASE_PERIOD, weights=weights, config=config)
    result = engine.calculate(observations=fares, current_period=CURRENT_PERIOD)

    print("=" * 60)
    print(f"National Airfare Price Index ({BASE_PERIOD}=100)")
    print("=" * 60)
    print(f"  Current period:      {result.current_period}")
    print(f"  National index:      {result.national_index:.2f}")
    print(f"  MoM change:          {result.mom_change_pct:+.2f}%")
    print(f"  YoY change:          {result.yoy_change_pct:+.2f}%" if result.yoy_change_pct is not None else "  YoY change:          n/a (no data 12 months prior)")
    print(f"  Routes covered:      {result.routes_covered}/{result.routes_total}")
    print(f"  Observations used:   {result.observations_used}")
    print(f"  Coverage rate:       {result.coverage_rate:.1%}")

    print("\nRoute-level indices:")
    for r in sorted(result.route_indices, key=lambda x: x.route):
        idx = f"{r.route_index:.2f}" if r.route_index is not None else "n/a"
        print(f"  {r.route:10s} status={r.status:18s} index={idx:>8s} n_obs={r.observations_used}")

    print("\nTop route contributions to this month's change:")
    for c in result.route_contributions[:5]:
        pts = f"{c.contribution_points:+.3f}" if c.contribution_points is not None else "n/a"
        print(f"  {c.route:10s} contribution={pts}")

    if result.quality_flags:
        print("\nQuality flags:")
        for flag in result.quality_flags:
            print(f"  - {flag}")

    print("\nCleaning report:")
    print(f"  {result.cleaning_report.total_input} in -> {result.cleaning_report.total_valid} used "
          f"({result.cleaning_report.total_removed} removed)")
    for reason, count in result.cleaning_report.removed_by_reason.items():
        print(f"    {reason}: {count}")

    out_path = Path(__file__).parent / "last_result.json"
    out_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
    print(f"\nFull structured result written to {out_path}")


if __name__ == "__main__":
    main()
