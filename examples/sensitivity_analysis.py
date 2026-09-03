"""Robustness / sensitivity analysis: how much does the national index move
under different, individually defensible methodological choices?

This is the answer to "how do you know your index isn't arbitrary?" — run
the same observations through several reasonable configurations and show
judges the spread. A methodology is credible if reasonable alternatives
land close together, not if one specific setting was cherry-picked.

Kept separate from the production engine (this script only *calls*
AirfarePriceIndex with different configs; it doesn't change any
calculation code). Run from the repo root:

    python examples/sensitivity_analysis.py
"""

from __future__ import annotations

import pandas as pd

from pathlib import Path

from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.traffic import build_dgca_weights
from index_engine.weighting import generate_synthetic_weights

from generate_sample_fares import generate

BASE_PERIOD = "2026-01"
CURRENT_PERIOD = "2026-08"
DGCA_CSV = Path(__file__).parent.parent / "data" / "traffic" / "dgca_domestic_city_pairs.csv"
COVERED_ROUTES = [
    ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
    ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
    ("CCU", "DEL"), ("BLR", "BOM"),
]


def run(fares: pd.DataFrame, weights: pd.DataFrame, label: str, **config_overrides) -> dict:
    config = IndexConfig(base_period=BASE_PERIOD, **config_overrides)
    engine = AirfarePriceIndex(base_period=BASE_PERIOD, weights=weights, config=config)
    result = engine.calculate(observations=fares, current_period=CURRENT_PERIOD)
    return {
        "label": label,
        "national_index": result.national_index,
        "routes_covered": result.routes_covered,
        "coverage_rate": result.coverage_rate,
    }


def main() -> None:
    fares = generate()
    routes = sorted((fares["origin"] + "-" + fares["destination"]).unique())
    weights = generate_synthetic_weights(routes)

    rows = [
        run(fares, weights, "Median + IQR outliers (default)", representative_method="median", outlier_method="iqr"),
        run(fares, weights, "Mean + IQR outliers", representative_method="mean", outlier_method="iqr"),
        run(fares, weights, "Median + MAD outliers", representative_method="median", outlier_method="mad"),
        run(fares, weights, "Median + percentile trim", representative_method="median", outlier_method="percentile"),
        run(fares, weights, "Median, no outlier removal", representative_method="median", outlier_method="none"),
        run(fares, weights, "Trimmed mean (10%) + IQR", representative_method="trimmed_mean", outlier_method="iqr"),
        run(fares, weights, "Median + IQR, geometric aggregation", representative_method="median", outlier_method="iqr", aggregation_method="geometric"),
        run(fares, weights, "Median + IQR, booking horizon 15-30 only", representative_method="median", outlier_method="iqr", booking_horizon_filter="15-30"),
    ]

    # Weight sensitivity: uniform weights instead of the metro-trunk-route bias.
    uniform_weights = weights.copy()
    uniform_weights["weight"] = 1.0
    rows.append(run(fares, uniform_weights, "Median + IQR, uniform route weights", representative_method="median", outlier_method="iqr"))

    # Real DGCA passenger-traffic weights vs. synthetic weights (same route universe).
    dgca_weights, diagnostics = build_dgca_weights(str(DGCA_CSV), COVERED_ROUTES)
    rows.append(run(fares, dgca_weights, "Median + IQR, REAL DGCA-derived weights", representative_method="median", outlier_method="iqr"))

    baseline = rows[0]["national_index"]

    print("=" * 78)
    print(f"Sensitivity analysis - National Index for {CURRENT_PERIOD} (base {BASE_PERIOD}=100)")
    print("=" * 78)
    header = f"{'Configuration':45s} {'Index':>8s} {'Delta vs default':>18s} {'Coverage':>10s}"
    print(header)
    print("-" * len(header))
    for row in rows:
        delta = row["national_index"] - baseline
        print(
            f"{row['label']:45s} {row['national_index']:8.2f} {delta:+18.2f} {row['coverage_rate']:9.1%}"
        )

    spread = max(r["national_index"] for r in rows) - min(r["national_index"] for r in rows)
    print("-" * len(header))
    print(f"Spread across all configurations: {spread:.2f} index points "
          f"({100 * spread / baseline:.2f}% of the default index value)")
    print(
        "\nInterpretation: a small spread across genuinely different but reasonable\n"
        "methodological choices supports that the headline number reflects real\n"
        "price movement rather than one arbitrarily chosen setting. This is a\n"
        "methodological sensitivity check on SYNTHETIC demonstration data, not\n"
        "evidence of real-world robustness.\n"
        "\n"
        "Note: 'no outlier removal' and 'percentile trim' can legitimately produce\n"
        "the IDENTICAL index value (verified, not a bug) when representative_method\n"
        "is median: tight percentile bounds on a small sample typically trim only\n"
        "the one or two most extreme points per tail, and the median of a group is\n"
        "often completely unaffected by removing its own tails. An identical number\n"
        "across two configs is not by itself proof that a config was misapplied."
    )

    print("\n" + "=" * 78)
    print("Synthetic vs. real DGCA-derived weights (same 10 routes)")
    print("=" * 78)
    print(f"Weighting window (real DGCA data): {diagnostics['weight_period_start']} to {diagnostics['weight_period_end']}")
    print(f"Real domestic network size in that window: {diagnostics['total_routes_in_window']} directional routes, "
          f"{diagnostics['total_passengers_in_window']:,.0f} total passengers")
    print(f"Traffic coverage of our 10 routes: {diagnostics['traffic_weight_coverage']:.2%} of India's domestic passenger traffic")
    synthetic_row = next(r for r in rows if "SYNTHETIC" not in r["label"].upper() and r["label"] == rows[0]["label"])
    dgca_row = next(r for r in rows if "DGCA" in r["label"].upper())
    print(f"National index with synthetic weights: {synthetic_row['national_index']:.2f}")
    print(f"National index with real DGCA weights: {dgca_row['national_index']:.2f}")
    print(f"Difference: {dgca_row['national_index'] - synthetic_row['national_index']:+.2f} index points")


if __name__ == "__main__":
    main()
