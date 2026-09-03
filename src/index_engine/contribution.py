"""Route contribution to the national index's month-over-month change.

For the ``arithmetic`` aggregation method, contributions are exact — they
sum to the national index's point change between the two periods, which is
what makes "route X drove Y% of this month's airfare inflation" a
defensible statement rather than a hand-wavy one — **provided the same set
of routes is OK (see quality.STATUS_OK) in both periods**. ``index.py``
raises a quality flag whenever that precondition doesn't hold (route
composition changed between the two periods being compared); when it does
hold, the renormalization below reproduces the exact point change.

Why renormalization is required at all: ``aggregation.national_index``
computes each period's national index as a weighted average over only the
routes usable *in that period* — i.e. it divides by the sum of
``weight_normalized`` over usable routes, not by 1.0. The raw
``weight_normalized`` on a ``RouteIndexResult`` sums to 1.0 across the
*entire* weights table, which is a different (usually larger) denominator
whenever route coverage is below 100% — the normal case, not an edge case
(see docs/methodology.md's own coverage examples). Multiplying a delta by
the raw table-wide weight therefore understates every contribution by
exactly the covered-weight fraction. Dividing by the same usable-weight
total that produced the current period's national index undoes that.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import RouteContribution, RouteIndexResult
from .quality import STATUS_OK


def _usable_weight_total(results: List[RouteIndexResult]) -> float:
    """Mirrors aggregation.national_index's own ``usable`` filter exactly,
    so the denominator used here always matches the denominator that
    actually produced that period's national index."""
    return sum(r.weight_normalized for r in results if r.route_index is not None and r.weight_normalized)


def compute_contributions(
    current_results: List[RouteIndexResult],
    previous_results: List[RouteIndexResult],
    aggregation_method: str,
) -> List[RouteContribution]:
    previous_by_route: Dict[str, RouteIndexResult] = {r.route: r for r in previous_results}

    # The current period's usable-weight total — the exact denominator
    # aggregation.national_index used to compute the current national
    # index. Renormalizing every route's weight by this (instead of the
    # raw, full-table weight_normalized) is what makes the sum below equal
    # the actual point change when route composition is unchanged between
    # periods; see module docstring.
    total_weight_current = _usable_weight_total(current_results)

    contributions: List[RouteContribution] = []
    for current in current_results:
        previous = previous_by_route.get(current.route)
        raw_weight = current.weight_normalized or 0.0
        weight = (raw_weight / total_weight_current) if total_weight_current else 0.0

        current_ok = current.status == STATUS_OK
        previous_ok = previous is not None and previous.status == STATUS_OK

        if not (current_ok and previous_ok):
            contributions.append(
                RouteContribution(
                    route=current.route,
                    weight_normalized=weight,
                    route_index_current=current.route_index,
                    route_index_previous=previous.route_index if previous else None,
                    contribution_points=None,
                )
            )
            continue

        if aggregation_method == "arithmetic":
            points = weight * (current.route_index - previous.route_index)
        elif aggregation_method == "geometric":
            # Approximate log-point contribution for a geometric aggregation;
            # exact decomposition of a geometric mean's change is nonlinear,
            # so this is reported as an approximation, not an exact split.
            import math

            points = weight * (math.log(current.route_index) - math.log(previous.route_index)) * 100
        else:
            raise ValueError(f"Unknown aggregation_method: {aggregation_method}")

        contributions.append(
            RouteContribution(
                route=current.route,
                weight_normalized=weight,
                route_index_current=current.route_index,
                route_index_previous=previous.route_index,
                contribution_points=points,
            )
        )

    contributions.sort(key=lambda c: abs(c.contribution_points) if c.contribution_points is not None else -1, reverse=True)
    return contributions
