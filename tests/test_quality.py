"""Tests for GET /api/v1/quality."""

from __future__ import annotations

import pytest


class TestQuality:
    """Tests for the data quality endpoint."""

    def test_successful_quality_report(self, client):
        """Returns 200 with a quality report."""
        resp = client.get("/api/v1/quality")
        assert resp.status_code == 200

        data = resp.json()
        expected_fields = {
            "total_observations", "valid", "rejected", "flagged",
            "rejection_reasons", "quality_score", "quality_grade",
            "route_health", "source_health", "data_source",
        }
        assert expected_fields.issubset(data.keys())

    def test_synthetic_label(self, client):
        """Quality report should be labeled synthetic."""
        resp = client.get("/api/v1/quality")
        data = resp.json()
        assert data["data_source"] == "synthetic"

    def test_quality_grade_valid(self, client):
        """Quality grade should be A-F."""
        resp = client.get("/api/v1/quality")
        data = resp.json()
        assert data["quality_grade"] in {"A", "B", "C", "D", "F"}

    def test_quality_score_range(self, client):
        """Quality score should be between 0 and 1."""
        resp = client.get("/api/v1/quality")
        data = resp.json()
        assert 0.0 <= data["quality_score"] <= 1.0

    def test_route_health_structure(self, client):
        """Each route health entry has expected fields."""
        resp = client.get("/api/v1/quality")
        data = resp.json()
        assert isinstance(data["route_health"], list)
        if data["route_health"]:
            rh = data["route_health"][0]
            expected = {"route", "observations", "valid", "rejected", "flagged", "health_score", "status"}
            assert expected.issubset(rh.keys())

    def test_source_health_structure(self, client):
        """Each source health entry has expected fields."""
        resp = client.get("/api/v1/quality")
        data = resp.json()
        assert isinstance(data["source_health"], list)
        if data["source_health"]:
            sh = data["source_health"][0]
            expected = {"source", "observations", "valid", "rejected", "reliability_score"}
            assert expected.issubset(sh.keys())

    def test_counts_add_up(self, client):
        """valid + rejected + flagged should equal total."""
        resp = client.get("/api/v1/quality")
        data = resp.json()
        assert data["valid"] + data["rejected"] + data["flagged"] == data["total_observations"]

    def test_response_is_json_serializable(self, client):
        """Full response should be JSON-serializable."""
        resp = client.get("/api/v1/quality")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
