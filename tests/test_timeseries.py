"""Tests for GET /api/v1/index/timeseries."""

from __future__ import annotations

import pytest


class TestTimeseries:
    """Tests for the timeseries endpoint."""

    def test_successful_range(self, client):
        """Valid date range returns 200 with data and pagination."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-01",
            "end_date": "2026-08",
        })
        assert resp.status_code == 200

        data = resp.json()
        assert "data" in data
        assert "pagination" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

        # Check structure of a point
        point = data["data"][0]
        assert "period" in point
        assert "index" in point
        assert "mom" in point
        assert "yoy" in point
        assert "data_source" in point

    def test_synthetic_label(self, client):
        """All timeseries points should be labeled synthetic."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-01",
            "end_date": "2026-03",
        })
        data = resp.json()
        assert data["data_source"] == "synthetic"
        for point in data["data"]:
            assert point["data_source"] == "synthetic"

    def test_pagination_metadata(self, client):
        """Pagination metadata should be correct."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-01",
            "end_date": "2026-08",
            "limit": 3,
            "offset": 0,
        })
        data = resp.json()
        pag = data["pagination"]
        assert pag["limit"] == 3
        assert pag["offset"] == 0
        assert pag["total"] == 8  # Jan through Aug = 8 months
        assert len(data["data"]) == 3
        assert pag["has_more"] is True

    def test_pagination_offset(self, client):
        """Offset should skip initial records."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-01",
            "end_date": "2026-08",
            "limit": 3,
            "offset": 6,
        })
        data = resp.json()
        assert len(data["data"]) == 2  # Only 2 remain (months 7 and 8)
        assert data["pagination"]["has_more"] is False

    def test_start_after_end_rejected(self, client):
        """start_date after end_date should return 400."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-08",
            "end_date": "2026-01",
        })
        assert resp.status_code == 400

    def test_missing_start_date(self, client):
        """Missing start_date should return 422."""
        resp = client.get("/api/v1/index/timeseries", params={
            "end_date": "2026-08",
        })
        assert resp.status_code == 422

    def test_missing_end_date(self, client):
        """Missing end_date should return 422."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-01",
        })
        assert resp.status_code == 422

    def test_invalid_date_format(self, client):
        """Invalid date format should return 422."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "January-2026",
            "end_date": "2026-08",
        })
        assert resp.status_code == 422

    def test_single_month_range(self, client):
        """A single-month range should return exactly 1 point."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-05",
            "end_date": "2026-05",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["period"] == "2026-05"

    def test_response_is_json_serializable(self, client):
        """Full response should be JSON-serializable."""
        resp = client.get("/api/v1/index/timeseries", params={
            "start_date": "2026-01",
            "end_date": "2026-03",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
