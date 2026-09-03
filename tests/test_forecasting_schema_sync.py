import dataclasses

from index_engine.models import IndexResult
from index_engine.route_analysis import RouteInflationRow
from index_engine.volatility import VolatilityResult

# Field names this module's build_forecasting_dataset() reads directly off
# IndexResult, kept in sync manually with data_access.py's national_rows.append(...).
INDEX_RESULT_FIELDS_USED = {
    "national_index",
    "mom_change_pct",
    "yoy_change_pct",
    "routes_covered",
    "routes_total",
    "coverage_rate",
    "observations_used",
    "observations_received",
    "observations_rejected",
    "outliers_flagged",
    "representative_method",
    "aggregation_method",
    "quality_flags",
    "route_indices",
}

# Field names read off VolatilityResult.
VOLATILITY_RESULT_FIELDS_USED = {"national_volatility", "national_classification"}

# Field names read off each RouteInflationRow (result.route_inflation entries).
ROUTE_INFLATION_ROW_FIELDS_USED = {
    "route",
    "origin",
    "destination",
    "status",
    "current_index",
    "mom_inflation_pct",
    "yoy_inflation_pct",
    "weight",
    "traffic_weight",
    "contribution",
    "volatility",
}


def test_index_result_still_has_every_field_this_module_depends_on():
    available = {f.name for f in dataclasses.fields(IndexResult)}
    missing = INDEX_RESULT_FIELDS_USED - available
    assert not missing, (
        f"index_engine.models.IndexResult is missing field(s) forecasting.data_access depends on: {missing}. "
        "Update NATIONAL_COLUMNS / build_forecasting_dataset() and this test's field list together."
    )


def test_volatility_result_still_has_every_field_this_module_depends_on():
    available = {f.name for f in dataclasses.fields(VolatilityResult)}
    missing = VOLATILITY_RESULT_FIELDS_USED - available
    assert not missing, (
        f"index_engine.volatility.VolatilityResult is missing field(s) forecasting.data_access depends on: "
        f"{missing}."
    )


def test_route_inflation_row_still_has_every_field_this_module_depends_on():
    available = {f.name for f in dataclasses.fields(RouteInflationRow)}
    missing = ROUTE_INFLATION_ROW_FIELDS_USED - available
    assert not missing, (
        f"index_engine.route_analysis.RouteInflationRow is missing field(s) forecasting.data_access depends "
        f"on: {missing}. Update ROUTE_COLUMNS / build_forecasting_dataset() and this test's field list together."
    )


# --- Fix 6: public API export surface -----------------------------------------


def test_forecasting_package_exports_status_constants():
    """Status constants must be reachable from the top-level `forecasting`
    package, not only from the submodules that define them — so a
    consumer checking `result.status == forecasting.STATUS_OK` doesn't
    need to know which internal module owns the constant."""
    import forecasting

    expected = {
        "STATUS_OK": "OK",
        "STATUS_INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
        "STATUS_MODEL_NOT_APPLICABLE": "MODEL_NOT_APPLICABLE",
        "STATUS_TARGET_UNAVAILABLE": "TARGET_UNAVAILABLE",
        "STATUS_INSUFFICIENT_OVERLAP": "INSUFFICIENT_OVERLAP",
    }
    for name, value in expected.items():
        assert hasattr(forecasting, name), f"forecasting.{name} is not exported"
        assert getattr(forecasting, name) == value
        assert name in forecasting.__all__


def test_forecasting_status_constants_are_not_duplicated_definitions():
    """The top-level export must be the SAME object as the submodule's
    definition (a re-export), not a second, independently-defined
    constant that could silently drift out of sync."""
    import forecasting
    import forecasting.results as results
    import forecasting.cpi_results as cpi_results

    assert forecasting.STATUS_OK is results.STATUS_OK
    assert forecasting.STATUS_INSUFFICIENT_DATA is results.STATUS_INSUFFICIENT_DATA
    assert forecasting.STATUS_MODEL_NOT_APPLICABLE is results.STATUS_MODEL_NOT_APPLICABLE
    assert forecasting.STATUS_TARGET_UNAVAILABLE is results.STATUS_TARGET_UNAVAILABLE
    assert forecasting.STATUS_INSUFFICIENT_OVERLAP is cpi_results.STATUS_INSUFFICIENT_OVERLAP


def test_every_name_in_all_actually_resolves():
    import forecasting

    missing = [name for name in forecasting.__all__ if not hasattr(forecasting, name)]
    assert missing == []
