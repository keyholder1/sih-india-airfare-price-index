"""Tests for POST /api/v1/index/calculate."""

from __future__ import annotations

import pytest
from tests.conftest import VALID_CALCULATE_REQUEST, VALID_OBSERVATION


class TestIndexCalculate:
    """Tests for the index calculation endpoint."""

    def test_successful_calculation(self, client):
        """Valid request returns 200 with expected fields."""
        resp = client.post("/api/v1/index/calculate", json=VALID_CALCULATE_REQUEST)
        assert resp.status_code == 200

        data = resp.json()
        assert "national_index" in data
        assert "mom" in data
        assert "yoy" in data
        assert "base_period" in data
        assert "current_period" in data
        assert "route_indices" in data
        assert isinstance(data["route_indices"], list)
        assert "data_source" in data
        assert "flags" in data
        assert "metadata" in data

    def test_synthetic_label(self, client):
        """Response is labeled as synthetic data."""
        resp = client.post("/api/v1/index/calculate", json=VALID_CALCULATE_REQUEST)
        data = resp.json()
        assert data["data_source"] == "synthetic"

        # Each route index should also be labeled
        for ri in data["route_indices"]:
            assert ri["data_source"] == "synthetic"

    def test_route_indices_match_input_routes(self, client):
        """Route indices should reflect the routes from the input."""
        resp = client.post("/api/v1/index/calculate", json=VALID_CALCULATE_REQUEST)
        data = resp.json()
        input_routes = {obs["route"] for obs in VALID_CALCULATE_REQUEST["observations"]}
        output_routes = {ri["route"] for ri in data["route_indices"]}
        assert input_routes == output_routes

    def test_empty_observations_rejected(self, client):
        """Empty observations list should be rejected (422)."""
        payload = {**VALID_CALCULATE_REQUEST, "observations": []}
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 422

    def test_missing_required_fields(self, client):
        """Missing base_period should return 422."""
        payload = {
            "observations": [VALID_OBSERVATION],
            "current_period": "2026-08",
        }
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 422

    def test_invalid_date_format(self, client):
        """Invalid date format in observations should return 422."""
        bad_obs = {**VALID_OBSERVATION, "date": "15-08-2026"}
        payload = {**VALID_CALCULATE_REQUEST, "observations": [bad_obs]}
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 422

    def test_invalid_period_format(self, client):
        """Invalid period format should return 422."""
        payload = {**VALID_CALCULATE_REQUEST, "base_period": "January 2026"}
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 422

    def test_negative_fare_rejected(self, client):
        """Negative fare should return 422."""
        bad_obs = {**VALID_OBSERVATION, "fare": -100}
        payload = {**VALID_CALCULATE_REQUEST, "observations": [bad_obs]}
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 422

    def test_zero_fare_rejected(self, client):
        """Zero fare should return 422."""
        bad_obs = {**VALID_OBSERVATION, "fare": 0}
        payload = {**VALID_CALCULATE_REQUEST, "observations": [bad_obs]}
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 422

    def test_multiple_observations(self, client):
        """Multiple observations across routes should work."""
        obs2 = {**VALID_OBSERVATION, "route": "BOM-BLR"}
        payload = {
            **VALID_CALCULATE_REQUEST,
            "observations": [VALID_OBSERVATION, obs2],
        }
        resp = client.post("/api/v1/index/calculate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["route_indices"]) == 2

    def test_response_is_json_serializable(self, client):
        """Response should be fully JSON-serializable (no datetime, Decimal, etc. issues)."""
        resp = client.post("/api/v1/index/calculate", json=VALID_CALCULATE_REQUEST)
        assert resp.status_code == 200
        # If json() succeeds, it's serializable
        data = resp.json()
        assert isinstance(data, dict)
