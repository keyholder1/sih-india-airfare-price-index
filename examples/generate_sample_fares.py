"""Generate SYNTHETIC DEMONSTRATION DATA for the index engine examples.

These numbers are fabricated for the SIH prototype demo. They do not
represent real airline pricing and must never be presented as such.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

random.seed(42)

ROUTES = [
    ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
    ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
    ("CCU", "DEL"), ("BLR", "BOM"),
]
AIRLINES = ["IndiGo", "AirIndia", "Vistara", "SpiceJet", "Akasa"]
FARE_CLASSES = ["Economy", "PremiumEconomy"]
FARE_TYPES = ["Refundable", "NonRefundable"]

PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]


def month_start(period: str) -> pd.Timestamp:
    return pd.Timestamp(period + "-01")


def generate(routes=None) -> pd.DataFrame:
    """``routes`` defaults to the original 10-route demo universe. Pass a
    different list of (origin, destination) IATA pairs to generate
    SYNTHETIC DEMONSTRATION DATA for a different route universe (e.g. for
    the route-coverage-expansion sensitivity comparison) — this never
    represents real fares for those routes, only illustrative ones with
    the same generation logic."""
    routes = routes if routes is not None else ROUTES
    # Base-fare level per route (INR), then a monthly drift + noise on top so
    # the index has something interesting to show. Computed per call (not at
    # import time) so a custom route list gets its own levels/drift.
    base_level = {route: random.randint(3500, 7500) for route in routes}
    monthly_drift_pct = {route: random.uniform(-0.01, 0.04) for route in routes}

    rows = []
    obs_id = 0
    for period in PERIODS:
        month_index = PERIODS.index(period)
        for origin, destination in routes:
            level = base_level[(origin, destination)] * ((1 + monthly_drift_pct[(origin, destination)]) ** month_index)
            n_obs = random.randint(20, 40)
            for _ in range(n_obs):
                flight_day_offset = random.randint(0, 27)
                flight_date = month_start(period) + pd.Timedelta(days=flight_day_offset)
                booking_horizon = random.choice([1, 2, 5, 10, 20, 40, 70])
                booking_date = flight_date - pd.Timedelta(days=booking_horizon)

                horizon_multiplier = 1.0 + max(0, (14 - booking_horizon)) * 0.015
                noise = random.gauss(1.0, 0.08)
                base_fare = max(500.0, level * horizon_multiplier * noise)
                taxes = round(base_fare * 0.12, 2)
                fees = round(random.uniform(150, 400), 2)
                total_fare = round(base_fare + taxes + fees, 2)

                obs_id += 1
                rows.append(
                    {
                        "observation_id": f"OBS{obs_id:06d}",
                        "timestamp": booking_date.isoformat(),
                        "source": random.choice(["airline_site", "mmt", "cleartrip", "goibibo"]),
                        "airline": random.choice(AIRLINES),
                        "origin": origin,
                        "destination": destination,
                        "flight_date": flight_date.strftime("%Y-%m-%d"),
                        "booking_date": booking_date.strftime("%Y-%m-%d"),
                        "fare_class": random.choice(FARE_CLASSES),
                        "fare_type": random.choice(FARE_TYPES),
                        "base_fare": round(base_fare, 2),
                        "taxes": taxes,
                        "fees": fees,
                        "total_fare": total_fare,
                        "currency": "INR",
                        "stops": random.choice([0, 0, 0, 1]),
                        "duration": round(random.uniform(1.2, 4.5), 2),
                        "baggage": random.choice(["15kg", "20kg", "25kg"]),
                        "availability": random.choice([True, True, True, False]),
                    }
                )

    # Inject a handful of extreme fares so outlier handling has something to catch.
    for _ in range(15):
        row = dict(rows[random.randint(0, len(rows) - 1)])
        row["observation_id"] = f"OBS{obs_id:06d}_OUTLIER"
        obs_id += 1
        row["total_fare"] = round(row["total_fare"] * random.uniform(4, 8), 2)
        rows.append(row)

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate()
    out_path = Path(__file__).parent / "sample_fares.csv"
    df.to_csv(out_path, index=False)
    print(f"SYNTHETIC DEMONSTRATION DATA written to {out_path} ({len(df)} rows)")
