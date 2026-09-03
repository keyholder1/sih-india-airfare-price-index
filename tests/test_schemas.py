"""Tests for Pydantic schema JSON serialization."""

from __future__ import annotations

import json

import pytest

from api.schemas import (
    IndexCalculateResponse,
    RouteIndexResponse,
    TimeseriesResponse,
    TimeseriesPointResponse,
    PaginationMeta,
    RouteListResponse,
    RouteAnalysisResponse,
    QualityResponse,
    RouteHealthResponse,
    SourceHealthResponse,
    RouteContextResponse,
    NewsEventResponse,
    DashboardSummaryResponse,
    CoverageInfo,
    AlertItem,
    ErrorResponse,
)


class TestSchemasSerialization:
    """Ensure every response model can round-trip through JSON."""

    def test_index_calculate_response(self):
        obj = IndexCalculateResponse(
            national_index=105.5,
            mom=1.2,
            yoy=3.5,
            base_period="2026-01",
            current_period="2026-08",
            route_indices=[
                RouteIndexResponse(
                    route="DEL-BOM", index=107.2, mom=1.5,
                    weight=0.25, contribution=26.8, data_source="synthetic",
                )
            ],
            quality_score=0.92,
            flags=["stub_data"],
            data_source="synthetic",
            metadata={"engine": "stub"},
        )
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["national_index"] == 105.5
        assert parsed["data_source"] == "synthetic"

    def test_timeseries_response(self):
        obj = TimeseriesResponse(
            data=[
                TimeseriesPointResponse(
                    period="2026-01", index=100.0, mom=None,
                    yoy=2.5, data_source="synthetic",
                )
            ],
            pagination=PaginationMeta(total=1, limit=100, offset=0, has_more=False),
            data_source="synthetic",
        )
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert len(parsed["data"]) == 1

    def test_route_list_response(self):
        obj = RouteListResponse(
            routes=[
                RouteAnalysisResponse(
                    route="DEL-BOM", route_index=107.2, mom=1.5,
                    weight=0.125, contribution=13.4,
                    traffic_coverage=0.85, status="active",
                    data_source="synthetic",
                )
            ],
            data_source="synthetic",
        )
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["routes"][0]["status"] == "active"

    def test_quality_response(self):
        obj = QualityResponse(
            total_observations=150,
            valid=135,
            rejected=7,
            flagged=8,
            rejection_reasons={"fare_out_of_range": 4},
            quality_score=0.90,
            quality_grade="A",
            route_health=[
                RouteHealthResponse(
                    route="DEL-BOM", observations=50, valid=45,
                    rejected=3, flagged=2, health_score=0.90, status="healthy",
                )
            ],
            source_health=[
                SourceHealthResponse(
                    source="source_a", observations=75, valid=68,
                    rejected=4, reliability_score=0.93,
                )
            ],
            data_source="synthetic",
        )
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["quality_grade"] == "A"

    def test_route_context_response(self):
        obj = RouteContextResponse(
            route="DEL-BOM",
            significant_movement=True,
            movement_direction="up",
            movement_pct=4.2,
            events=[
                NewsEventResponse(
                    headline="Test headline",
                    source="test_source",
                    publication_date="2026-08-14",
                    url=None,
                    relevance_score=0.87,
                    data_source="synthetic",
                )
            ],
            data_source="synthetic",
        )
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["route"] == "DEL-BOM"
        assert parsed["events"][0]["url"] is None

    def test_dashboard_summary_response(self):
        route = RouteAnalysisResponse(
            route="DEL-BOM", route_index=107.2, mom=1.5,
            weight=0.125, contribution=13.4,
            traffic_coverage=0.85, status="active",
            data_source="synthetic",
        )
        quality = QualityResponse(
            total_observations=150, valid=135, rejected=7, flagged=8,
            rejection_reasons={}, quality_score=0.90, quality_grade="A",
            route_health=[], source_health=[], data_source="synthetic",
        )
        obj = DashboardSummaryResponse(
            index=105.5, mom=1.2, yoy=3.5,
            routes=[route],
            top_increases=[route],
            top_decreases=[route],
            top_contributors=[route],
            quality=quality,
            coverage=CoverageInfo(total_routes=8, active_routes=6, average_coverage=0.72),
            alerts=[AlertItem(level="info", message="Test alert", timestamp=None)],
            data_source="synthetic",
        )
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["index"] == 105.5
        assert len(parsed["alerts"]) == 1

    def test_error_response(self):
        obj = ErrorResponse(detail="Something went wrong.")
        raw = obj.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["detail"] == "Something went wrong."
