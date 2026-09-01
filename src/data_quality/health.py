"""Source health (is the scraper actually working?) and route health
(are this route's raw observations trustworthy?).

``route_attempts`` is an optional, separate input — a log of what the
scraper *tried*, not what it returned. Fare observations alone can't tell
you "we asked for BLR-IXL and got nothing back"; only the scraper's own
request log can. Without it, source health still reports everything
derivable from the observations themselves (received/valid/flagged/
rejected, freshness), and ``routes_requested``/``routes_successful``/
``route_success_rate`` are left as ``None`` (not 0 — 0 would claim total
failure the data quality layer has no basis to claim).

Expected shape of ``route_attempts`` (list of dicts or a DataFrame), one
row per source:

    {
        "source": "airline_A",
        "routes_requested": 50,
        "routes_successful": 47,
        "routes_attempted": ["BLR-DEL", "DEL-BOM", ...],  # optional, enables overall_route_coverage
    }
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union

import pandas as pd

from . import reason_codes as rc
from .config import DataQualityConfig
from .models import RouteHealth, SourceHealth

RouteAttempts = Union[pd.DataFrame, Sequence[dict]]

_FALLBACK_SOURCE = "UNKNOWN_SOURCE"


def _route_attempts_by_source(route_attempts: Optional[RouteAttempts]) -> Dict[str, dict]:
    if route_attempts is None:
        return {}
    if isinstance(route_attempts, pd.DataFrame):
        rows = route_attempts.to_dict("records")
    else:
        rows = list(route_attempts)
    return {row["source"]: row for row in rows if "source" in row}


def compute_source_health(
    work: pd.DataFrame,
    route_attempts: Optional[RouteAttempts],
    config: DataQualityConfig,
    reference_time: Optional[pd.Timestamp] = None,
) -> List[SourceHealth]:
    attempts_by_source = _route_attempts_by_source(route_attempts)

    grouped = work.copy()
    grouped["_dq_source"] = grouped["source"] if "source" in grouped.columns else _FALLBACK_SOURCE
    grouped["_dq_source"] = grouped["_dq_source"].fillna(_FALLBACK_SOURCE).replace("", _FALLBACK_SOURCE)

    results: List[SourceHealth] = []
    for source, group in grouped.groupby("_dq_source"):
        received = len(group)
        valid = int((group["status"] == rc.STATUS_VALID).sum())
        flagged = int((group["status"] == rc.STATUS_FLAGGED).sum())
        rejected = int((group["status"] == rc.STATUS_REJECTED).sum())
        validity_rate = valid / received if received else 0.0

        oldest = newest = None
        data_age_seconds = None
        if "timestamp" in group.columns:
            # utc=True normalizes every parsed value to tz-aware UTC
            # regardless of whether the source's timestamp string carried an
            # offset (a real scraper's ISO-8601-with-offset output) or not
            # (this prototype's naive synthetic fixtures) — otherwise mixing
            # the two raises "Cannot subtract tz-naive and tz-aware
            # datetime-like objects" below. A naive input is treated as UTC.
            ts = pd.to_datetime(group["timestamp"], errors="coerce", format="mixed", utc=True).dropna()
            if len(ts):
                oldest, newest = ts.min(), ts.max()
                ref = reference_time if reference_time is not None else pd.Timestamp.now(tz="UTC")
                if ref.tzinfo is None:
                    ref = ref.tz_localize("UTC")
                data_age_seconds = max(0.0, (ref - newest).total_seconds())

        attempt = attempts_by_source.get(source)
        routes_requested = routes_successful = routes_failed = None
        route_success_rate = None
        if attempt is not None:
            routes_requested = attempt.get("routes_requested")
            routes_successful = attempt.get("routes_successful")
            if routes_requested is not None and routes_successful is not None:
                routes_failed = attempt.get("routes_failed", routes_requested - routes_successful)
                route_success_rate = routes_successful / routes_requested if routes_requested else 0.0

        status = _classify_source_status(
            received=received,
            validity_rate=validity_rate,
            route_success_rate=route_success_rate,
            config=config,
        )

        results.append(
            SourceHealth(
                source=source,
                status=status,
                observations_received=received,
                valid_observations=valid,
                flagged_observations=flagged,
                rejected_observations=rejected,
                observation_validity_rate=validity_rate,
                routes_requested=routes_requested,
                routes_successful=routes_successful,
                routes_failed=routes_failed,
                route_success_rate=route_success_rate,
                oldest_observation=oldest.isoformat() if oldest is not None else None,
                newest_observation=newest.isoformat() if newest is not None else None,
                data_age_seconds=data_age_seconds,
            )
        )

    return sorted(results, key=lambda s: s.source)


def _classify_source_status(
    *, received: int, validity_rate: float, route_success_rate: Optional[float], config: DataQualityConfig
) -> str:
    if received == 0:
        return rc.HEALTH_FAILED
    if route_success_rate is not None and route_success_rate == 0:
        return rc.HEALTH_FAILED
    degraded = validity_rate < config.degraded_validity_rate_threshold
    if route_success_rate is not None:
        degraded = degraded or route_success_rate < config.degraded_route_success_rate_threshold
    return rc.HEALTH_DEGRADED if degraded else rc.HEALTH_HEALTHY


def overall_route_success_rate(source_health: List[SourceHealth]) -> Optional[float]:
    weighted = [(s.route_success_rate, s.routes_requested) for s in source_health if s.route_success_rate is not None]
    if not weighted:
        return None
    total_requested = sum(requested for _, requested in weighted)
    if not total_requested:
        return None
    return sum(rate * requested for rate, requested in weighted) / total_requested


def overall_route_coverage(route_attempts: Optional[RouteAttempts], observed_routes: set) -> Optional[float]:
    attempts_by_source = _route_attempts_by_source(route_attempts)
    attempted_routes = set()
    for attempt in attempts_by_source.values():
        attempted_routes.update(attempt.get("routes_attempted", []) or [])
    if not attempted_routes:
        return None
    return len(attempted_routes & observed_routes) / len(attempted_routes)


def compute_route_health(
    work: pd.DataFrame,
    config: DataQualityConfig,
    base_period: Optional[str] = None,
    current_period: Optional[str] = None,
) -> List[RouteHealth]:
    results: List[RouteHealth] = []

    has_period_info = base_period is not None and "_dq_flight_date" in work.columns
    if has_period_info:
        period = work["_dq_flight_date"].dt.strftime("%Y-%m")

    for route, group in work.groupby("_dq_route"):
        total = len(group)
        rejected = int((group["status"] == rc.STATUS_REJECTED).sum())
        valid = total - rejected  # VALID + FLAGGED
        quality_rate = valid / total if total else 0.0

        required_complete = ~group["rejection_reason"].isin(
            {
                rc.MISSING_OBSERVATION_ID,
                rc.MISSING_AIRLINE,
                rc.MISSING_ORIGIN,
                rc.MISSING_DESTINATION,
                rc.MISSING_CURRENCY,
            }
        )
        data_completeness = float(required_complete.mean()) if total else 0.0

        has_base = has_current = None
        if has_period_info:
            route_period = period.loc[group.index]
            has_base = bool((route_period == base_period).any())
            has_current = bool((route_period == current_period).any()) if current_period else None

        origin, _, destination = route.partition("-")
        results.append(
            RouteHealth(
                route=route,
                origin=origin,
                destination=destination,
                observations_total=total,
                observations_valid=valid,
                observations_rejected=rejected,
                route_quality_rate=quality_rate,
                data_completeness=data_completeness,
                has_base_period_data=has_base,
                has_current_period_data=has_current,
            )
        )

    return sorted(results, key=lambda r: r.route)
