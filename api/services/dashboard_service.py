"""
Service adapter for the Dashboard Summary endpoint.

Composes results from the index, route, and quality engines into
a single dashboard payload. Contains NO business logic — only
assembly.
"""

from __future__ import annotations

from src.engine.factory import (
    get_index_engine,
    get_route_analytics_engine,
    get_quality_engine,
)
from api.schemas import (
    DashboardSummaryResponse,
    RouteAnalysisResponse,
    QualityResponse,
    RouteHealthResponse,
    SourceHealthResponse,
    CoverageInfo,
    AlertItem,
)


def get_dashboard_summary() -> DashboardSummaryResponse:
    """Assemble the dashboard summary from all available engines."""

    # ── Index snapshot ────────────────────────────────────────────
    index_engine = get_index_engine()
    # Use a minimal synthetic calculation for the dashboard headline.
    # In production the dashboard would read the latest pre-computed index.
    ts = index_engine.get_timeseries(start_date="2026-07", end_date="2026-08")
    if ts:
        latest = ts[-1]
        national_index = latest.index
        mom = latest.mom
        yoy = latest.yoy
    else:
        national_index = 100.0
        mom = None
        yoy = None

    # ── Route analysis ────────────────────────────────────────────
    route_engine = get_route_analytics_engine()
    raw_routes = route_engine.get_route_analysis()

    route_responses = [
        RouteAnalysisResponse(
            route=ra.route,
            route_index=ra.route_index,
            mom=ra.mom,
            weight=ra.weight,
            contribution=ra.contribution,
            traffic_coverage=ra.traffic_coverage,
            status=ra.status,
            data_source=ra.data_source,
        )
        for ra in raw_routes
    ]

    # Sort for top movers
    by_mom = sorted(
        [r for r in route_responses if r.mom is not None],
        key=lambda r: r.mom,  # type: ignore[arg-type]
        reverse=True,
    )
    top_increases = by_mom[:3]
    top_decreases = list(reversed(by_mom[-3:])) if len(by_mom) >= 3 else list(reversed(by_mom))

    # Sort for top contributors
    top_contributors = sorted(
        route_responses,
        key=lambda r: r.contribution,
        reverse=True,
    )[:3]

    # ── Quality ───────────────────────────────────────────────────
    quality_engine = get_quality_engine()
    qr = quality_engine.assess_quality([])

    quality = QualityResponse(
        total_observations=qr.total_observations,
        valid=qr.valid,
        rejected=qr.rejected,
        flagged=qr.flagged,
        rejection_reasons=qr.rejection_reasons,
        quality_score=qr.quality_score,
        quality_grade=qr.quality_grade,
        route_health=[
            RouteHealthResponse(
                route=rh.route,
                observations=rh.observations,
                valid=rh.valid,
                rejected=rh.rejected,
                flagged=rh.flagged,
                health_score=rh.health_score,
                status=rh.status,
            )
            for rh in qr.route_health
        ],
        source_health=[
            SourceHealthResponse(
                source=sh.source,
                observations=sh.observations,
                valid=sh.valid,
                rejected=sh.rejected,
                reliability_score=sh.reliability_score,
            )
            for sh in qr.source_health
        ],
        data_source=qr.data_source,
    )

    # ── Coverage ──────────────────────────────────────────────────
    active_routes = [r for r in route_responses if r.status == "active"]
    coverage = CoverageInfo(
        total_routes=len(route_responses),
        active_routes=len(active_routes),
        average_coverage=(
            round(sum(r.traffic_coverage for r in active_routes) / len(active_routes), 4)
            if active_routes
            else 0.0
        ),
    )

    # ── Overall data provenance ──────────────────────────────────
    # "real" only if every contributing engine actually used real data --
    # a dashboard mixing real and synthetic sources must not claim "real".
    sub_sources = {r.data_source for r in route_responses} | {quality.data_source}
    overall_data_source = "real" if sub_sources == {"real"} else "synthetic"

    # ── Alerts ────────────────────────────────────────────────────
    if overall_data_source == "synthetic":
        alert_message = (
            "Dashboard is using synthetic/demo data -- no real scraped "
            "observations are loaded yet. See src/engine/data_access.py."
        )
    else:
        alert_message = "Dashboard reflects real scraped observations."
    alerts: list[AlertItem] = [
        AlertItem(level="info", message=alert_message, timestamp=None),
    ]

    return DashboardSummaryResponse(
        index=national_index,
        mom=mom,
        yoy=yoy,
        routes=route_responses,
        top_increases=top_increases,
        top_decreases=top_decreases,
        top_contributors=top_contributors,
        quality=quality,
        coverage=coverage,
        alerts=alerts,
        data_source=overall_data_source,
    )
