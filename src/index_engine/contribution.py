"""Route contribution to the national index's month-over-month change.

For the ``arithmetic`` aggregation method, contributions are exact: they
sum to the national index's point change between the two periods, which is
what makes "route X drove Y% of this month's airfare inflation" a
defensible statement rather than a hand-wavy one.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import RouteContribution, RouteIndexResult
from .quality import STATUS_OK


def compute_contributions(
    current_results: List[RouteIndexResult],
    previous_results: List[RouteIndexResult],
    aggregation_method: str,
) -> List[RouteContribution]:
    previous_by_route: Dict[str, RouteIndexResult] = {r.route: r for r in previous_results}

    contributions: List[RouteContribution] = []
    for current in current_results:
        previous = previous_by_route.get(current.route)
        weight = current.weight_normalized or 0.0

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
