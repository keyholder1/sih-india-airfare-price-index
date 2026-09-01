"""Tests for GET /api/v1/dashboard/summary."""

from __future__ import annotations

import pytest


class TestDashboard:
    """Tests for the dashboard summary endpoint."""

    def test_successful_summary(self, client):
        """Returns 200 with all dashboard fields."""
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200

        data = resp.json()
        expected_fields = {
            "index", "mom", "yoy", "routes",
            "top_increases", "top_decreases", "top_contributors",
            "quality", "coverage", "alerts", "data_source",
        }
        assert expected_fields.issubset(data.keys())

    def test_synthetic_label(self, client):
        """Dashboard should be labeled synthetic."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert data["data_source"] == "synthetic"

    def test_routes_present(self, client):
        """Routes list should be non-empty."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert isinstance(data["routes"], list)
        assert len(data["routes"]) > 0

    def test_top_movers_present(self, client):
        """Top increases and decreases should be present."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert isinstance(data["top_increases"], list)
        assert isinstance(data["top_decreases"], list)
        assert len(data["top_increases"]) > 0
        assert len(data["top_decreases"]) > 0

    def test_top_contributors_present(self, client):
        """Top contributors should be present."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert isinstance(data["top_contributors"], list)
        assert len(data["top_contributors"]) > 0

    def test_quality_section(self, client):
        """Quality section has expected fields."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        q = data["quality"]
        expected = {
            "total_observations", "valid", "rejected", "flagged",
            "quality_score", "quality_grade", "data_source",
        }
        assert expected.issubset(q.keys())

    def test_coverage_section(self, client):
        """Coverage section has expected fields."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        c = data["coverage"]
        expected = {"total_routes", "active_routes", "average_coverage"}
        assert expected.issubset(c.keys())

    def test_alerts_present(self, client):
        """Alerts should contain at least the stub data warning."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert isinstance(data["alerts"], list)
        assert len(data["alerts"]) > 0
        assert any("synthetic" in a["message"].lower() for a in data["alerts"])

    def test_response_is_json_serializable(self, client):
        """Full response should be JSON-serializable."""
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
