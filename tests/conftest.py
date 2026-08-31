"""Shared test helpers.

Builds minimal, valid fare-observation dicts so individual tests only need
to override the one or two fields they actually care about.
"""

from __future__ import annotations

from itertools import count

import pandas as pd

_counter = count(1)


def make_observation(**overrides) -> dict:
    obs = {
        "observation_id": f"OBS{next(_counter):06d}",
        "timestamp": "2026-01-01T00:00:00",
        "source": "airline_site",
        "airline": "IndiGo",
        "origin": "BLR",
        "destination": "DEL",
        "flight_date": "2026-01-15",
        "booking_date": "2026-01-01",
        "fare_class": "Economy",
        "fare_type": "NonRefundable",
        "base_fare": 4400.0,
        "taxes": 500.0,
        "fees": 100.0,
        "total_fare": 5000.0,
        "currency": "INR",
        "stops": 0,
        "duration": 2.5,
        "baggage": "15kg",
        "availability": True,
    }
    obs.update(overrides)
    return obs


def make_observations(n: int, **overrides) -> list:
    return [make_observation(**overrides) for _ in range(n)]


def to_df(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows)
