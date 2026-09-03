"""Per-route status classification and overall quality/coverage metrics.

No route is ever silently dropped: every route that has a weight or that
appears in the data gets a :class:`RouteIndexResult` with an explicit
``status``, even when no numeric index could be computed for it.
"""

from __future__ import annotations

from typing import List

from .models import RouteIndexResult

STATUS_OK = "OK"
STATUS_NO_BASE_DATA = "NO_BASE_DATA"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
STATUS_NEW_ROUTE = "NEW_ROUTE"
#: Had base-period data, but none for the period being classified (whether
#: that's the queried "current" period, or a prev-month/prev-year
#: comparison period — index.py._classify uses this same status for all
#: three, there is no separate "no current data" status).
STATUS_DISCONTINUED = "DISCONTINUED"


def compute_quality_flags(route_results: List[RouteIndexResult], cleaning_removed: int, total_input: int) -> List[str]:
    flags: List[str] = []

    no_base = [r.route for r in route_results if r.status == STATUS_NO_BASE_DATA]
    if no_base:
        flags.append(f"{len(no_base)} route(s) have no base-period data: {sorted(no_base)}")

    insufficient = [r.route for r in route_results if r.status == STATUS_INSUFFICIENT_DATA]
    if insufficient:
        flags.append(f"{len(insufficient)} route(s) have insufficient observations: {sorted(insufficient)}")

    new_routes = [r.route for r in route_results if r.status == STATUS_NEW_ROUTE]
    if new_routes:
        flags.append(f"{len(new_routes)} route(s) are new since the base period: {sorted(new_routes)}")

    discontinued = [r.route for r in route_results if r.status == STATUS_DISCONTINUED]
    if discontinued:
        flags.append(f"{len(discontinued)} route(s) appear discontinued: {sorted(discontinued)}")

    if total_input > 0:
        removed_pct = 100.0 * cleaning_removed / total_input
        if removed_pct > 20:
            flags.append(f"{removed_pct:.1f}% of input observations were removed during validation/cleaning")

    return flags


def coverage_rate(route_results: List[RouteIndexResult]) -> float:
    """Fraction of total route weight for which a usable index exists.

    Weighted, not a raw route count, because a handful of thin routes
    missing data matters far less than a major trunk route missing data.
    """
    total_weight = sum(r.weight_normalized or 0.0 for r in route_results)
    if total_weight == 0:
        return 0.0
    covered_weight = sum(r.weight_normalized or 0.0 for r in route_results if r.status == STATUS_OK)
    return covered_weight / total_weight
