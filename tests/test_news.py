"""Tests for GET /api/v1/routes/{route}/context."""

from __future__ import annotations

import pytest


class TestNewsContext:
    """Tests for the news/context endpoint."""

    def test_successful_context(self, client):
        """Known route returns 200 with context data."""
        resp = client.get("/api/v1/routes/DEL-BOM/context")
        assert resp.status_code == 200

        data = resp.json()
        expected_fields = {
            "route", "significant_movement", "movement_direction",
            "movement_pct", "events", "data_source",
        }
        assert expected_fields.issubset(data.keys())

    def test_synthetic_label(self, client):
        """Context and events should be labeled synthetic."""
        resp = client.get("/api/v1/routes/DEL-BOM/context")
        data = resp.json()
        assert data["data_source"] == "synthetic"
        for event in data["events"]:
            assert event["data_source"] == "synthetic"

    def test_events_structure(self, client):
        """Each event has expected fields."""
        resp = client.get("/api/v1/routes/DEL-BOM/context")
        data = resp.json()
        assert isinstance(data["events"], list)
        assert len(data["events"]) > 0

        event = data["events"][0]
        expected = {"headline", "source", "publication_date", "url", "relevance_score", "data_source"}
        assert expected.issubset(event.keys())

    def test_unknown_route_returns_404(self, client):
        """Unknown route code should return 404."""
        resp = client.get("/api/v1/routes/XXX-YYY/context")
        assert resp.status_code == 404

    def test_relevance_score_range(self, client):
        """Relevance scores should be between 0 and 1."""
        resp = client.get("/api/v1/routes/DEL-BOM/context")
        data = resp.json()
        for event in data["events"]:
            assert 0.0 <= event["relevance_score"] <= 1.0

    def test_movement_direction_values(self, client):
        """Movement direction should be 'up', 'down', or null."""
        resp = client.get("/api/v1/routes/DEL-BOM/context")
        data = resp.json()
        assert data["movement_direction"] in {"up", "down", None}

    def test_response_is_json_serializable(self, client):
        """Full response should be JSON-serializable."""
        resp = client.get("/api/v1/routes/DEL-BOM/context")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
