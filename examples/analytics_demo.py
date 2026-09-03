"""Unified demo: price index + volatility + route inflation + affordability,
using REAL DGCA-derived route weights (not synthetic) and synthetic
demonstration fares/income (clearly labeled where they are).

Run from the repo root:

    python examples/analytics_demo.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from index_engine import AirfareAnalytics, IndexConfig
from index_engine.traffic import build_dgca_weights

from generate_sample_fares import generate

BASE_PERIOD = "2026-01"
CURRENT_PERIOD = "2026-08"
DGCA_CSV = Path(__file__).parent.parent / "data" / "traffic" / "dgca_domestic_city_pairs.csv"
COVERED_ROUTES = [
    ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
    ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
    ("CCU", "DEL"), ("BLR", "BOM"),
]


def synthetic_income_series() -> pd.DataFrame:
    """SYNTHETIC DEMONSTRATION DATA — not a real wage/income series. Exists
    only to demonstrate the affordability calculation end to end; replace
    with a validated Indian income/wage index before drawing any real
    conclusion from the affordability number."""
    periods = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    values = [100, 100.4, 100.9, 101.5, 102.0, 102.4, 102.8, 103.2]
    return pd.DataFrame(
        {"period": periods, "indicator": "income_index", "value": values, "source": "SYNTHETIC_DEMONSTRATION_DATA"}
    )


def fmt_pct(value):
    return f"{value:+.2f}%" if value is not None else "n/a"


def main() -> None:
    fares = generate()
    engine_weights, diagnostics = build_dgca_weights(str(DGCA_CSV), COVERED_ROUTES)
    config = IndexConfig(base_period=BASE_PERIOD, representative_method="median", outlier_method="iqr")

    analytics = AirfareAnalytics(
        base_period=BASE_PERIOD,
        weights=engine_weights,
        config=config,
        traffic_weight_coverage=diagnostics["traffic_weight_coverage"],
    )
    result = analytics.calculate(fares, current_period=CURRENT_PERIOD, income_series=synthetic_income_series())

    idx = result.price_index
    vol = result.volatility

    print("=" * 60)
    print(" INDIA AIRFARE MARKET ANALYTICS (prototype)")
    print("=" * 60)

    print("\nAIRFARE PRICE INDEX")
    print(f"Index:                 {idx.national_index:.2f}")
    print(f"MoM:                   {fmt_pct(idx.mom_change_pct)}")
    print(f"YoY:                   {fmt_pct(idx.yoy_change_pct)}")

    print("\nDATA COVERAGE")
    print(f"Observations used:     {idx.observations_used:,}")
    print(f"Routes covered:        {idx.routes_covered}/{idx.routes_total}")
    print(f"Traffic coverage:      {result.traffic_weight_coverage:.1%} of India's domestic passenger traffic "
          f"(real DGCA data, {diagnostics['weight_period_start']} to {diagnostics['weight_period_end']})")

    print("\n" + "-" * 43)
    print("VOLATILITY")
    print("-" * 43)
    print(f"National volatility:   {vol.national_volatility:.3f} ({vol.method})")
    print(f"Classification:        {vol.national_classification}")
    if vol.high_volatility_routes:
        print("Most volatile routes:")
        for route in vol.high_volatility_routes[:3]:
            print(f"  - {route}")
    if vol.booking_horizon_volatility:
        print("Volatility by booking horizon:")
        for b in vol.booking_horizon_volatility:
            v = f"{b.volatility:.3f}" if b.volatility is not None else "n/a"
            print(f"  {b.bucket:8s} volatility={v:>6s}  classification={b.classification}")

    print("\n" + "-" * 43)
    print("ROUTE INFLATION")
    print("-" * 43)
    highest = result.rankings["highest_mom_inflation"][:3]
    lowest = result.rankings["lowest_mom_inflation"][:3]
    print("Highest MoM inflation:")
    for r in highest:
        print(f"  {r.route:10s} {fmt_pct(r.mom_inflation_pct)}  (traffic weight: {r.traffic_weight:.2%})" if r.traffic_weight else f"  {r.route:10s} {fmt_pct(r.mom_inflation_pct)}")
    print("Lowest MoM inflation:")
    for r in lowest:
        print(f"  {r.route:10s} {fmt_pct(r.mom_inflation_pct)}  (traffic weight: {r.traffic_weight:.2%})" if r.traffic_weight else f"  {r.route:10s} {fmt_pct(r.mom_inflation_pct)}")

    print("\nMost economically important movers (by contribution, not raw inflation):")
    for r in result.rankings["largest_positive_contributors"][:2] + result.rankings["largest_negative_contributors"][:2]:
        print(f"  {r.route:10s} contribution={r.contribution:+.3f}  inflation={fmt_pct(r.mom_inflation_pct)}  traffic weight={r.traffic_weight:.2%}")

    print("\n" + "-" * 43)
    print("AFFORDABILITY (relative to SYNTHETIC DEMONSTRATION income series)")
    print("-" * 43)
    aff = result.affordability
    print(f"Airfare index:         {aff.airfare_index:.2f}")
    print(f"Income index:          {aff.income_index:.2f}")
    print(f"Relative affordability:{aff.relative_affordability_index:.2f}")
    print(f"Status:                {aff.status} (income data is illustrative only)")
    print("-" * 43)


if __name__ == "__main__":
    main()
