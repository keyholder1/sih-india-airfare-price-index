"""
Stub implementations of the engine protocols.

Every value returned is clearly marked ``data_source="synthetic"``.
These exist purely for development and testing — swap them out via
``src/engine/factory.py`` when the real modules are ready.
"""

from __future__ import annotations

from typing import Any, Optional

from src.engine.protocols import (
    IndexResult,
    RouteIndex,
    TimeseriesPoint,
    QualityReport,
    RouteHealth,
    SourceHealth,
    RouteAnalysis,
    RouteContext,
    NewsEvent,
)

# A fixed set of representative Indian air routes used by the stubs.
_STUB_ROUTES = [
    "DEL-BOM",
    "DEL-BLR",
    "BOM-BLR",
    "DEL-CCU",
    "BOM-HYD",
    "DEL-MAA",
    "BLR-HYD",
    "CCU-BOM",
]

_DATA_SOURCE = "synthetic"


class StubIndexEngine:
    """Stub implementation of ``IndexEngineProtocol``."""

    def calculate_index(
        self,
        observations: list[dict[str, Any]],
        base_period: str,
        current_period: str,
        config: Optional[dict[str, Any]] = None,
    ) -> IndexResult:
        # Derive unique routes from the observations that were passed in
        routes_seen = list({obs.get("route", "UNKNOWN") for obs in observations})
        if not routes_seen:
            routes_seen = _STUB_ROUTES[:3]

        n = len(routes_seen)
        weight = round(1.0 / n, 4) if n else 0.0

        route_indices = [
            RouteIndex(
                route=r,
                index=round(100.0 + i * 2.5, 2),
                mom=round(0.5 + i * 0.3, 2),
                weight=weight,
                contribution=round(weight * (100.0 + i * 2.5), 2),
                data_source=_DATA_SOURCE,
            )
            for i, r in enumerate(routes_seen)
        ]

        national = round(
            sum(ri.index * ri.weight for ri in route_indices), 2
        )

        return IndexResult(
            national_index=national,
            mom=1.2,
            yoy=3.5,
            base_period=base_period,
            current_period=current_period,
            route_indices=route_indices,
            quality_score=0.92,
            data_source=_DATA_SOURCE,
            flags=["stub_data"],
            metadata={"engine": "stub", "observation_count": len(observations)},
        )

    def get_timeseries(
        self,
        start_date: str,
        end_date: str,
    ) -> list[TimeseriesPoint]:
        # Generate monthly points between start and end.
        points: list[TimeseriesPoint] = []
        # Simple parse: YYYY-MM
        try:
            s_year, s_month = int(start_date[:4]), int(start_date[5:7])
            e_year, e_month = int(end_date[:4]), int(end_date[5:7])
        except (ValueError, IndexError):
            return points

        year, month = s_year, s_month
        idx = 100.0
        prev_idx = None

        while (year, month) <= (e_year, e_month):
            mom = round(((idx - prev_idx) / prev_idx) * 100, 2) if prev_idx else None
            yoy = round(2.0 + (month % 3) * 0.5, 2)  # synthetic seasonal pattern

            points.append(
                TimeseriesPoint(
                    period=f"{year:04d}-{month:02d}",
                    index=round(idx, 2),
                    mom=mom,
                    yoy=yoy,
                    data_source=_DATA_SOURCE,
                )
            )

            prev_idx = idx
            idx += 0.8 + (month % 4) * 0.3  # synthetic trend

            month += 1
            if month > 12:
                month = 1
                year += 1

        return points


class StubDataQualityEngine:
    """Stub implementation of ``DataQualityProtocol``."""

    def assess_quality(
        self,
        observations: list[dict[str, Any]],
    ) -> QualityReport:
        total = len(observations) if observations else 150  # synthetic default
        valid = int(total * 0.90)
        rejected = int(total * 0.05)
        flagged = total - valid - rejected

        routes_seen = list({obs.get("route", "UNKNOWN") for obs in observations}) if observations else _STUB_ROUTES[:3]

        route_health = [
            RouteHealth(
                route=r,
                observations=total // max(len(routes_seen), 1),
                valid=valid // max(len(routes_seen), 1),
                rejected=rejected // max(len(routes_seen), 1),
                flagged=flagged // max(len(routes_seen), 1),
                health_score=round(0.85 + i * 0.02, 2),
                status="healthy" if i < len(routes_seen) - 1 else "degraded",
            )
            for i, r in enumerate(routes_seen)
        ]

        source_health = [
            SourceHealth(
                source="source_a",
                observations=total // 2,
                valid=valid // 2,
                rejected=rejected // 2,
                reliability_score=0.93,
            ),
            SourceHealth(
                source="source_b",
                observations=total - total // 2,
                valid=valid - valid // 2,
                rejected=rejected - rejected // 2,
                reliability_score=0.88,
            ),
        ]

        return QualityReport(
            total_observations=total,
            valid=valid,
            rejected=rejected,
            flagged=flagged,
            rejection_reasons={
                "fare_out_of_range": rejected // 2,
                "duplicate": rejected - rejected // 2,
            },
            quality_score=0.90,
            quality_grade="A",
            route_health=route_health,
            source_health=source_health,
            data_source=_DATA_SOURCE,
        )


class StubRouteAnalyticsEngine:
    """Stub implementation of ``RouteAnalyticsProtocol``."""

    def get_route_analysis(self) -> list[RouteAnalysis]:
        return [
            RouteAnalysis(
                route=r,
                route_index=round(100.0 + i * 3.0, 2),
                mom=round(0.3 + i * 0.5, 2),
                weight=round(1.0 / len(_STUB_ROUTES), 4),
                contribution=round((1.0 / len(_STUB_ROUTES)) * (100.0 + i * 3.0), 2),
                traffic_coverage=round(0.85 - i * 0.05, 2),
                status="active" if i < 6 else "new",
                data_source=_DATA_SOURCE,
            )
            for i, r in enumerate(_STUB_ROUTES)
        ]


class StubNewsContextEngine:
    """Stub implementation of ``NewsContextProtocol``."""

    # Routes for which we pretend to have context
    _KNOWN_ROUTES = set(_STUB_ROUTES)

    async def get_route_context(self, route_code: str) -> RouteContext:
        if route_code not in self._KNOWN_ROUTES:
            raise ValueError(f"Unknown route: {route_code}")

        return RouteContext(
            route=route_code,
            significant_movement=True,
            movement_direction="up",
            movement_pct=4.2,
            events=[
                NewsEvent(
                    headline=f"Synthetic: Airfares on {route_code} rise amid holiday demand",
                    source="synthetic_news_source",
                    publication_date="2026-08-14",
                    url=None,
                    relevance_score=0.87,
                    data_source=_DATA_SOURCE,
                ),
                NewsEvent(
                    headline=f"Synthetic: New airline capacity added on {route_code}",
                    source="synthetic_news_source",
                    publication_date="2026-08-10",
                    url=None,
                    relevance_score=0.72,
                    data_source=_DATA_SOURCE,
                ),
            ],
            data_source=_DATA_SOURCE,
        )
