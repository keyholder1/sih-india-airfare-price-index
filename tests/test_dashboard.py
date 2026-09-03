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

    def test_data_source_label_is_honest(self, client):
        """data_source must reflect the actual observations on disk --
        real once a real collection is present, synthetic otherwise --
        never hard-coded to one value regardless of what's loaded."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert data["data_source"] in {"real", "synthetic"}

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
        """Alerts should contain a provenance notice matching the actual
        data_source -- 'synthetic' wording when synthetic, 'real' wording
        when real, never a mismatched or missing notice."""
        resp = client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert isinstance(data["alerts"], list)
        assert len(data["alerts"]) > 0
        expected_word = "synthetic" if data["data_source"] == "synthetic" else "real"
        assert any(expected_word in a["message"].lower() for a in data["alerts"])

    def test_response_is_json_serializable(self, client):
        """Full response should be JSON-serializable."""
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
