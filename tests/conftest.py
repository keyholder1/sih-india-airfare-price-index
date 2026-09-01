"""
Shared test fixtures.
"""

from __future__ import annotations

import os
import sys

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


# ── Sample data ───────────────────────────────────────────────────

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
