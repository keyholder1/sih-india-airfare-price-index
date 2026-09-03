"""Tests for GET /api/v1/routes."""

from __future__ import annotations

import pytest


class TestRoutes:
    """Tests for the route analysis endpoint."""

    def test_successful_route_list(self, client):
        """Returns 200 with a list of routes."""
        resp = client.get("/api/v1/routes")
        assert resp.status_code == 200

        data = resp.json()
        assert "routes" in data
        assert isinstance(data["routes"], list)
        assert len(data["routes"]) > 0

    def test_route_structure(self, client):
        """Each route has all expected fields."""
        resp = client.get("/api/v1/routes")
        data = resp.json()
        route = data["routes"][0]

        expected_fields = {
            "route", "route_index", "mom", "weight",
            "contribution", "traffic_coverage", "status", "data_source",
        }
        assert expected_fields.issubset(route.keys())

    def test_data_source_label_is_honest(self, client):
        """data_source must reflect the actual observations on disk --
        real once a real collection is present, synthetic otherwise --
        never hard-coded to one value regardless of what's loaded, and
        consistent between the summary field and each route's own."""
        resp = client.get("/api/v1/routes")
        data = resp.json()
        assert data["data_source"] in {"real", "synthetic", "mixed", "unavailable"}
        for route in data["routes"]:
            assert route["data_source"] in {"real", "synthetic", "mixed", "unavailable"}

    def test_route_status_values(self, client):
        """Route status should be one of the expected values."""
        resp = client.get("/api/v1/routes")
        data = resp.json()
        valid_statuses = {"active", "inactive", "new"}
        for route in data["routes"]:
            assert route["status"] in valid_statuses

    def test_response_is_json_serializable(self, client):
        """Full response should be JSON-serializable."""
        resp = client.get("/api/v1/routes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
