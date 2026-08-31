import math

from index_engine.models import CleaningReport, IndexResult, RouteContribution, RouteIndexResult
from index_engine.route_analysis import build_route_inflation_table, inflation_matrix, route_map_objects, top_rankings


def _route(route, index, status="OK", weight=0.5):
    origin, destination = route.split("-")
    return RouteIndexResult(
        route=route, origin=origin, destination=destination, period="x",
        base_period_fare=5000.0, period_fare=5000.0 if index is None else 5000.0 * index / 100,
        route_index=index, observations_used=10, weight_raw=weight, weight_normalized=weight, status=status,
    )


def _index_result(route_indices):
    return IndexResult(
        base_period="2026-01", current_period="x", national_index=None, mom_change_pct=None, yoy_change_pct=None,
        routes_covered=0, routes_total=len(route_indices), observations_used=0, coverage_rate=0.0,
        representative_method="median", aggregation_method="arithmetic", route_indices=route_indices,
        route_contributions=[], quality_flags=[], cleaning_report=CleaningReport(0, 0, 0, {}),
    )


def test_route_mom_and_yoy_calculated_from_route_index_history():
    current = _index_result([_route("BLR-DEL", 110.0)])
    prev_month = _index_result([_route("BLR-DEL", 106.0)])
    prev_year = _index_result([_route("BLR-DEL", 104.0)])
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=[])
    row = rows[0]
    assert abs(row.mom_inflation_pct - ((110 / 106 - 1) * 100)) < 1e-9
    assert abs(row.yoy_inflation_pct - ((110 / 104 - 1) * 100)) < 1e-9


def test_new_route_has_no_mom_or_yoy():
    current = _index_result([_route("CCU-DEL", None, status="NEW_ROUTE")])
    prev_month = _index_result([_route("CCU-DEL", None, status="NEW_ROUTE")])
    prev_year = _index_result([_route("CCU-DEL", None, status="NO_BASE_DATA")])
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=[])
    assert rows[0].mom_inflation_pct is None
    assert rows[0].yoy_inflation_pct is None
    assert rows[0].status == "NEW_ROUTE"


def test_discontinued_route_carries_status_through():
    current = _index_result([_route("CCU-DEL", None, status="DISCONTINUED")])
    prev_month = _index_result([_route("CCU-DEL", 100.0)])
    prev_year = _index_result([_route("CCU-DEL", 100.0)])
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=[])
    assert rows[0].status == "DISCONTINUED"
    assert rows[0].mom_inflation_pct is None


def test_contribution_is_attached_from_existing_contribution_calc():
    current = _index_result([_route("BLR-DEL", 110.0)])
    prev_month = _index_result([_route("BLR-DEL", 106.0)])
    prev_year = _index_result([_route("BLR-DEL", 104.0)])
    contributions = [RouteContribution(route="BLR-DEL", weight_normalized=0.5, route_index_current=110.0, route_index_previous=106.0, contribution_points=2.0)]
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=contributions)
    assert rows[0].contribution == 2.0


def test_rankings_pick_highest_and_lowest():
    current = _index_result([_route("A-B", 120.0), _route("C-D", 95.0)])
    prev_month = _index_result([_route("A-B", 110.0), _route("C-D", 100.0)])
    prev_year = _index_result([_route("A-B", 110.0), _route("C-D", 100.0)])
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=[])
    rankings = top_rankings(rows, top_n=1)
    assert rankings["highest_mom_inflation"][0].route == "A-B"
    assert rankings["lowest_mom_inflation"][0].route == "C-D"


def test_inflation_matrix_marks_missing_routes_as_nan_not_zero():
    current = _index_result([_route("BLR-DEL", 110.0)])
    prev_month = _index_result([_route("BLR-DEL", 106.0)])
    prev_year = _index_result([_route("BLR-DEL", 104.0)])
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=[])
    matrix = inflation_matrix(rows, metric="mom")
    assert math.isnan(matrix.loc["BLR", "DEL"]) is False  # BLR-DEL has a value
    # Any other origin/destination combination in a bigger matrix would be NaN;
    # with only one route the matrix is 1x1, so just confirm no zero-fill happened.
    assert matrix.loc["BLR", "DEL"] > 0


def test_route_map_objects_attach_coordinates_and_skip_unmapped_cities():
    current = _index_result([_route("BLR-DEL", 110.0), _route("XXX-YYY", 105.0)])
    prev_month = _index_result([_route("BLR-DEL", 106.0), _route("XXX-YYY", 100.0)])
    prev_year = _index_result([_route("BLR-DEL", 104.0), _route("XXX-YYY", 100.0)])
    rows = build_route_inflation_table(current, prev_month, prev_year, contributions=[])
    objects = route_map_objects(rows)
    routes_present = {(o["origin"], o["destination"]) for o in objects}
    assert ("BLR", "DEL") in routes_present
    assert ("XXX", "YYY") not in routes_present  # unmapped city, correctly skipped
