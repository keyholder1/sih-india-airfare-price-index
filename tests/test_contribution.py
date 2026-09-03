"""Regression tests for route contribution decomposition
(index_engine.contribution.compute_contributions).

Covers the partial-coverage exactness bug: contributions must sum to the
national index's point change whenever the same set of routes is OK in
both periods being compared — including when that set is a strict, always
-the-same subset of the full weights table (i.e. coverage is permanently
below 100%, not just temporarily). A prior version of this function used
the raw, full-table ``weight_normalized`` instead of renormalizing over
the usable-in-this-period subset the way ``aggregation.national_index``
does, which silently understated every contribution by the covered-weight
fraction with no quality flag raised.
"""

import pandas as pd

from index_engine.config import IndexConfig
from index_engine.contribution import compute_contributions
from index_engine.index import AirfarePriceIndex
from index_engine.models import RouteIndexResult


def _route_result(route, index, weight_normalized, status="OK"):
    origin, destination = route.split("-")
    return RouteIndexResult(
        route=route, origin=origin, destination=destination, period="x",
        base_period_fare=5000.0, period_fare=None if index is None else 5000.0 * index / 100,
        route_index=index, observations_used=10, weight_raw=weight_normalized, weight_normalized=weight_normalized,
        status=status,
    )


def test_contributions_sum_exactly_under_permanently_partial_coverage():
    # BLR-DEL is the only route ever OK; CCU-MAA is in the weights table
    # (raw weight 0.4 of 1.0) but never has data, in either period — so
    # the *set* of OK routes is identical (unchanged) across both periods,
    # which is exactly the precondition under which contribution.py's
    # module docstring promises an exact sum.
    current = [
        _route_result("BLR-DEL", 120.0, weight_normalized=0.6, status="OK"),
        _route_result("CCU-MAA", None, weight_normalized=0.4, status="NO_BASE_DATA"),
    ]
    previous = [
        _route_result("BLR-DEL", 100.0, weight_normalized=0.6, status="OK"),
        _route_result("CCU-MAA", None, weight_normalized=0.4, status="NO_BASE_DATA"),
    ]
    contributions = compute_contributions(current, previous, aggregation_method="arithmetic")

    # national_index() for each period, restricted to the usable (OK)
    # subset, renormalizes by 0.6 (the only usable weight) -> national
    # index is just BLR-DEL's own route_index each period: 120.0 and 100.0.
    national_current = 120.0
    national_previous = 100.0
    expected_delta = national_current - national_previous  # 20.0 points

    total_contribution = sum(c.contribution_points for c in contributions if c.contribution_points is not None)
    assert abs(total_contribution - expected_delta) < 1e-9

    blr_del = next(c for c in contributions if c.route == "BLR-DEL")
    # Renormalized weight is 0.6 / 0.6 = 1.0 (BLR-DEL is the *entire*
    # usable-this-period basket), not the raw table weight of 0.6.
    assert abs(blr_del.weight_normalized - 1.0) < 1e-9
    assert abs(blr_del.contribution_points - 20.0) < 1e-9


def test_contributions_sum_exactly_end_to_end_with_permanently_uncovered_route():
    """Same scenario, but through the real AirfarePriceIndex.calculate()
    pipeline end to end, reproducing the exact numbers the audit found
    wrong (previously: sum understated by the covered-weight fraction)."""
    rows = []
    for period, flight_date, fare in [
        ("2026-01", "2026-01-15", 5000.0),
        ("2026-07", "2026-07-15", 5200.0),
        ("2026-08", "2026-08-15", 5500.0),
    ]:
        for i in range(4):
            rows.append(
                {
                    "observation_id": f"o-{period}-{i}", "airline": "IndiGo", "origin": "BLR", "destination": "DEL",
                    "flight_date": flight_date, "booking_date": "2026-01-01", "total_fare": fare, "currency": "INR",
                }
            )
    weights = pd.DataFrame(
        [
            {"origin": "BLR", "destination": "DEL", "weight": 0.6},
            # CCU-MAA is in the weights table but never appears in the
            # observations above -- permanently zero coverage.
            {"origin": "CCU", "destination": "MAA", "weight": 0.4},
        ]
    )
    engine = AirfarePriceIndex(
        base_period="2026-01", weights=weights,
        config=IndexConfig(base_period="2026-01", min_observations_per_route_period=1, aggregation_method="arithmetic"),
    )
    result = engine.calculate(pd.DataFrame(rows), current_period="2026-08")

    total_contribution = sum(c.contribution_points for c in result.route_contributions if c.contribution_points is not None)
    prev_month_national = result.national_index / (1 + result.mom_change_pct / 100)
    expected_delta = result.national_index - prev_month_national

    assert abs(total_contribution - expected_delta) < 1e-6
    # No spurious MoM "route composition changed" flag: CCU-MAA is
    # consistently NOT OK in current vs. prev-month, so the OK set used by
    # compute_contributions never changes between those two periods. (A
    # YoY composition-change flag is expected and irrelevant here -- no
    # prior-year data was provided at all, which is a separate concern
    # from this test's partial-coverage scenario.)
    assert not any("between 2026-07 and 2026-08" in f for f in result.quality_flags)


def test_contributions_still_sum_exactly_at_full_coverage():
    # Two routes, both always OK -> renormalization is a no-op (divides by
    # 1.0), preserving the existing full-coverage behaviour exactly.
    current = [
        _route_result("BLR-DEL", 110.0, weight_normalized=0.5, status="OK"),
        _route_result("DEL-BOM", 105.0, weight_normalized=0.5, status="OK"),
    ]
    previous = [
        _route_result("BLR-DEL", 100.0, weight_normalized=0.5, status="OK"),
        _route_result("DEL-BOM", 100.0, weight_normalized=0.5, status="OK"),
    ]
    contributions = compute_contributions(current, previous, aggregation_method="arithmetic")
    total_contribution = sum(c.contribution_points for c in contributions)
    national_current = 0.5 * 110.0 + 0.5 * 105.0
    national_previous = 0.5 * 100.0 + 0.5 * 100.0
    assert abs(total_contribution - (national_current - national_previous)) < 1e-9


def test_non_ok_route_keeps_raw_share_of_usable_weight_and_no_contribution_points():
    current = [
        _route_result("BLR-DEL", 110.0, weight_normalized=0.6, status="OK"),
        _route_result("CCU-DEL", None, weight_normalized=0.4, status="NEW_ROUTE"),
    ]
    previous = [
        _route_result("BLR-DEL", 100.0, weight_normalized=0.6, status="OK"),
        _route_result("CCU-DEL", None, weight_normalized=0.4, status="NEW_ROUTE"),
    ]
    contributions = compute_contributions(current, previous, aggregation_method="arithmetic")
    ccu_del = next(c for c in contributions if c.route == "CCU-DEL")
    assert ccu_del.contribution_points is None
    # Still reported with the renormalized weight (share of the *usable*
    # basket) for transparency, even though it has no contribution_points.
    assert abs(ccu_del.weight_normalized - (0.4 / 0.6)) < 1e-9
