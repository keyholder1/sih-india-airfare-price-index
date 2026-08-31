"""Example charts built on top of the index engine's output.

Deliberately kept separate from index_engine itself — the engine returns
plain data structures, and this script is just one consumer of them. Run
from the repo root:

    python examples/visualize.py

Produces examples/charts.png with five panels:
  1. National index over time
  2. Route-level index comparison (latest period)
  3. MoM inflation over time
  4. YoY inflation over time
  5. Route contribution to the latest month's index change
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from index_engine import AirfarePriceIndex, IndexConfig
from index_engine.weighting import generate_synthetic_weights

from generate_sample_fares import PERIODS, generate

BASE_PERIOD = "2026-01"


def build_series(fares: pd.DataFrame):
    routes = sorted((fares["origin"] + "-" + fares["destination"]).unique())
    weights = generate_synthetic_weights(routes)
    config = IndexConfig(base_period=BASE_PERIOD, representative_method="median", outlier_method="iqr")
    engine = AirfarePriceIndex(base_period=BASE_PERIOD, weights=weights, config=config)

    national = []
    mom = []
    results_by_period = {}
    for period in PERIODS:
        result = engine.calculate(observations=fares, current_period=period)
        results_by_period[period] = result
        national.append(result.national_index)
        mom.append(result.mom_change_pct)
    return results_by_period, national, mom


def main() -> None:
    fares = generate()
    results_by_period, national, mom = build_series(fares)
    latest_period = PERIODS[-1]
    latest = results_by_period[latest_period]

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle("Airfare Price Index — SYNTHETIC DEMONSTRATION DATA (not real market prices)", fontsize=12)

    # 1. National index over time
    ax = axes[0, 0]
    ax.plot(PERIODS, national, marker="o")
    ax.axhline(100, color="grey", linestyle="--", linewidth=1)
    ax.set_title("National Airfare Price Index")
    ax.set_ylabel(f"Index ({BASE_PERIOD}=100)")
    ax.tick_params(axis="x", rotation=45)

    # 2. Route-level index comparison (latest period)
    ax = axes[0, 1]
    route_rows = sorted(latest.route_indices, key=lambda r: r.route)
    labels = [r.route for r in route_rows]
    values = [r.route_index if r.route_index is not None else 0 for r in route_rows]
    ax.bar(labels, values)
    ax.axhline(100, color="grey", linestyle="--", linewidth=1)
    ax.set_title(f"Route-level Index ({latest_period})")
    ax.tick_params(axis="x", rotation=90)

    # 3. MoM inflation over time
    ax = axes[0, 2]
    ax.bar(PERIODS, [m if m is not None else 0 for m in mom])
    ax.axhline(0, color="grey", linewidth=1)
    ax.set_title("Month-over-Month Change (%)")
    ax.tick_params(axis="x", rotation=45)

    # 4. YoY inflation (only periods with 12 months of history)
    ax = axes[1, 0]
    yoy_periods = [p for p in PERIODS if results_by_period[p].yoy_change_pct is not None]
    yoy_values = [results_by_period[p].yoy_change_pct for p in yoy_periods]
    if yoy_values:
        ax.bar(yoy_periods, yoy_values, color="tab:orange")
    else:
        ax.text(0.5, 0.5, "No YoY data\n(< 12 months of history)", ha="center", va="center")
    ax.axhline(0, color="grey", linewidth=1)
    ax.set_title("Year-over-Year Change (%)")
    ax.tick_params(axis="x", rotation=45)

    # 5. Route contribution to latest month's change
    ax = axes[1, 1]
    contributions = [c for c in latest.route_contributions if c.contribution_points is not None][:8]
    ax.barh([c.route for c in contributions], [c.contribution_points for c in contributions], color="tab:green")
    ax.axvline(0, color="grey", linewidth=1)
    ax.set_title(f"Route Contribution to {latest_period} Change (points)")
    ax.invert_yaxis()

    axes[1, 2].axis("off")

    fig.tight_layout()
    out_path = Path(__file__).parent / "charts.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
