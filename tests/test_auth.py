"""Tests for API key authentication."""

from __future__ import annotations

import pytest


class TestAuth:
    """Tests for API key authentication on /api/v1/ routes."""

    def test_missing_api_key_returns_401(self, no_auth_client):
        """Request without X-API-Key header should return 401 (or 422)."""
        resp = no_auth_client.get("/api/v1/routes")
        # FastAPI returns 422 for missing required header
        assert resp.status_code in {401, 422}

    def test_wrong_api_key_returns_401(self, no_auth_client):
        """Request with incorrect API key should return 401."""
        resp = no_auth_client.get(
            "/api/v1/routes",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_correct_api_key_returns_200(self, client):
        """Request with correct API key should succeed."""
        resp = client.get("/api/v1/routes")
        assert resp.status_code == 200

    def test_health_check_no_auth(self, no_auth_client):
        """Health check should not require auth."""
        resp = no_auth_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_auth_required_on_all_v1_routes(self, no_auth_client):
        """All /api/v1/ endpoints should reject unauthenticated requests."""
        endpoints = [
            ("GET", "/api/v1/routes"),
            ("GET", "/api/v1/quality"),
            ("GET", "/api/v1/dashboard/summary"),
            ("GET", "/api/v1/index/timeseries?start_date=2026-01&end_date=2026-08"),
            ("GET", "/api/v1/routes/DEL-BOM/context"),
        ]
        for method, url in endpoints:
            if method == "GET":
                resp = no_auth_client.get(url)
            else:
                resp = no_auth_client.post(url)
            assert resp.status_code in {401, 422}, f"{method} {url} returned {resp.status_code}"
