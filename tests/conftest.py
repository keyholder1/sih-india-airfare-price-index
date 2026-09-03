"""Shared test fixtures and helpers.

Combines the API test client fixtures (backend endpoint tests) with the
minimal fare-observation builders (engine/data-quality/scraper tests) so
individual tests only need to override the one or two fields they
actually care about.
"""

from __future__ import annotations

import os
import sys
from itertools import count

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Ensure the project root is on sys.path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required env vars BEFORE importing the app
os.environ.setdefault("API_KEY", "test-key-12345")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from api.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient with a valid API key header pre-configured."""
    c = TestClient(app)
    c.headers.update({"X-API-Key": "test-key-12345"})
    return c


@pytest.fixture()
def no_auth_client() -> TestClient:
    """Return a TestClient without any API key header."""
    return TestClient(app)


# ── API sample data ─────────────────────────────────────────────────

VALID_OBSERVATION = {
    "route": "DEL-BOM",
    "fare": 4500.0,
    "date": "2026-08-15",
    "source": "real",
}

VALID_CALCULATE_REQUEST = {
    "observations": [VALID_OBSERVATION],
    "base_period": "2026-01",
    "current_period": "2026-08",
    "config": {},
}


# ── Engine/data-quality/scraper fare-observation builders ───────────

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
