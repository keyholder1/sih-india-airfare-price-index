"""Six example charts built on top of AirfareAnalytics. Static matplotlib
placeholders for what the frontend team will eventually render properly
(a real map, an interactive heatmap) — the point here is that all the
underlying numbers already exist and are chart-ready.

Run from the repo root:

    python examples/analytics_visuals.py

Produces examples/analytics_charts.png with:
  1. Airfare index over time
  2. Route volatility (latest period)
  3. Volatility by booking horizon
  4. Route inflation origin x destination heatmap (MoM)
  5. Airfare index vs income index vs relative affordability
  6. Real DGCA passenger-traffic weight by route
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from index_engine import AirfareAnalytics, IndexConfig
from index_engine.traffic import build_dgca_weights

from analytics_demo import COVERED_ROUTES, DGCA_CSV, synthetic_income_series
from generate_sample_fares import PERIODS, generate

BASE_PERIOD = "2026-01"


def main() -> None:
    fares = generate()
    engine_weights, diagnostics = build_dgca_weights(str(DGCA_CSV), COVERED_ROUTES)
    config = IndexConfig(base_period=BASE_PERIOD, representative_method="median", outlier_method="iqr")
    analytics = AirfareAnalytics(
        base_period=BASE_PERIOD, weights=engine_weights, config=config,
        traffic_weight_coverage=diagnostics["traffic_weight_coverage"],
    )
    income_series = synthetic_income_series()

    results_by_period = {
        period: analytics.calculate(fares, current_period=period, income_series=income_series)
        for period in PERIODS
    }
    latest = results_by_period[PERIODS[-1]]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(
        "India Airfare Market Analytics - SYNTHETIC fares/income, REAL DGCA traffic weights",
        fontsize=12,
    )

    # 1. Airfare index over time
    ax = axes[0, 0]
    national = [results_by_period[p].price_index.national_index for p in PERIODS]
    ax.plot(PERIODS, national, marker="o")
    ax.axhline(100, color="grey", linestyle="--", linewidth=1)
    ax.set_title("Airfare Price Index")
    ax.tick_params(axis="x", rotation=45)

    # 2. Route volatility (latest period)
    ax = axes[0, 1]
    vol_rows = sorted(latest.volatility.route_volatility, key=lambda r: r.route)
    labels = [r.route for r in vol_rows]
    values = [r.volatility if r.volatility is not None else 0 for r in vol_rows]
    colors = ["tab:red" if r.classification == "HIGH" else "tab:orange" if r.classification == "MODERATE" else "tab:green" for r in vol_rows]
    ax.bar(labels, values, color=colors)
    ax.set_title(f"Route Volatility ({PERIODS[-1]}, coefficient of variation)")
    ax.tick_params(axis="x", rotation=90)

    # 3. Volatility by booking horizon
    ax = axes[0, 2]
    bh_rows = latest.volatility.booking_horizon_volatility
    bh_labels = [b.bucket for b in bh_rows]
    bh_values = [b.volatility if b.volatility is not None else 0 for b in bh_rows]
    ax.bar(bh_labels, bh_values, color="tab:purple")
    ax.set_title("Volatility by Booking Horizon")
    ax.tick_params(axis="x", rotation=45)

    # 4. Route inflation heatmap (origin x destination, MoM %)
    ax = axes[1, 0]
    matrix = latest.inflation_matrix(metric="mom")
    masked = np.ma.masked_invalid(matrix.to_numpy(dtype=float))
    im = ax.imshow(masked, cmap="RdYlGn_r", aspect="auto")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=90)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix.iat[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:+.1f}%", ha="center", va="center", fontsize=7)
    ax.set_title("Route Inflation Heatmap (MoM %, blank = no data)")
    fig.colorbar(im, ax=ax, fraction=0.046)

    # 5. Airfare index vs income index vs relative affordability
    ax = axes[1, 1]
    income_by_period = dict(zip(income_series["period"], income_series["value"]))
    income_values = [income_by_period.get(p) for p in PERIODS]
    affordability_values = [
        results_by_period[p].affordability.relative_affordability_index if results_by_period[p].affordability else None
        for p in PERIODS
    ]
    ax.plot(PERIODS, national, marker="o", label="Airfare index")
    ax.plot(PERIODS, income_values, marker="s", label="Income index (synthetic)")
    ax.plot(PERIODS, affordability_values, marker="^", label="Relative affordability")
    ax.axhline(100, color="grey", linestyle="--", linewidth=1)
    ax.set_title("Airfare vs Income vs Relative Affordability")
    ax.legend(fontsize=7)
    ax.tick_params(axis="x", rotation=45)

    # 6. Real DGCA passenger-traffic weight by route
    ax = axes[1, 2]
    traffic_weights = engine_weights.sort_values("national_weight", ascending=False)
    ax.bar(traffic_weights["origin"] + "-" + traffic_weights["destination"], traffic_weights["national_weight"] * 100, color="tab:blue")
    ax.set_title("Real DGCA National Traffic Weight (%)")
    ax.tick_params(axis="x", rotation=90)

    fig.tight_layout()
    out_path = Path(__file__).parent / "analytics_charts.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
