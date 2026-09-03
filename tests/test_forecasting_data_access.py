import pandas as pd
import pytest

from conftest import make_observation, to_df
from forecasting import build_forecasting_dataset, derive_calendar_periods
from index_engine.exceptions import InsufficientDataError
from index_engine.quality import STATUS_DISCONTINUED, STATUS_NEW_ROUTE, STATUS_OK


def _route_rows(origin, destination, flight_date, fare, n=5, **overrides):
    return [
        make_observation(
            origin=origin,
            destination=destination,
            flight_date=flight_date,
            booking_date=pd.Timestamp(flight_date) - pd.Timedelta(days=10),
            total_fare=fare + i,
            **overrides,
        )
        for i in range(n)
    ]


# --- derive_calendar_periods -------------------------------------------------


def test_derive_calendar_periods_covers_full_range_with_no_gaps():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-04-15", 5200.0)
    periods = derive_calendar_periods(to_df(rows))
    # Jan, Feb, Mar, Apr must ALL appear even though Feb/Mar have zero rows.
    assert periods == ["2026-01", "2026-02", "2026-03", "2026-04"]


def test_derive_calendar_periods_uses_flight_date_not_booking_date():
    row = make_observation(flight_date="2026-06-15", booking_date="2026-01-01")
    periods = derive_calendar_periods(to_df([row]))
    assert periods == ["2026-06"]


def test_derive_calendar_periods_empty_for_no_data():
    assert derive_calendar_periods(pd.DataFrame(columns=["flight_date"])) == []


# --- build_forecasting_dataset: basic shape ----------------------------------


def test_national_table_has_one_row_per_requested_period():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-02-15", 5100.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    assert list(dataset.national["period"]) == ["2026-01", "2026-02"]
    assert len(dataset.national) == 2


def test_route_table_keeps_a_row_for_every_period_even_when_route_has_no_data():
    """A gap month (Mar has zero observations for this route) must still
    produce a row — with a non-OK status — not silently disappear."""
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-03-15", 5300.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    series = dataset.route_series("BLR-DEL")
    assert list(series["period"]) == ["2026-01", "2026-02", "2026-03"]
    feb_row = series[series["period"] == "2026-02"].iloc[0]
    assert feb_row["status"] != STATUS_OK
    assert pd.isna(feb_row["route_index"])


def test_known_index_value_matches_manual_calculation():
    """Sanity check that this layer reshapes, and does not alter, the
    engine's own numbers (same fixture as index_engine's own test)."""
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-08-15", 5500.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    row = dataset.route_series("BLR-DEL", ok_only=True)
    aug = row[row["period"] == "2026-08"].iloc[0]
    assert abs(aug["route_index"] - 110.0) < 0.5


# --- status preservation ------------------------------------------------------


def test_new_route_status_is_preserved_not_dropped():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("CCU", "DEL", "2026-03-15", 4000.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    ccu_row = dataset.route_series("CCU-DEL")
    ccu_row = ccu_row[ccu_row["period"] == "2026-03"].iloc[0]
    assert ccu_row["status"] == STATUS_NEW_ROUTE
    assert pd.isna(ccu_row["route_index"])


def test_discontinued_route_status_is_preserved_not_dropped():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)  # only in the base period
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01", "2026-02"])
    row = dataset.route_series("BLR-DEL")
    feb = row[row["period"] == "2026-02"].iloc[0]
    assert feb["status"] == STATUS_DISCONTINUED
    assert pd.isna(feb["route_index"])


def test_nothing_is_filled_or_interpolated():
    """A period with no data anywhere must not have its route_index
    guessed from neighbouring periods."""
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-03-15", 6000.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    series = dataset.route_series("BLR-DEL")
    feb = series[series["period"] == "2026-02"].iloc[0]
    assert pd.isna(feb["route_index"])  # not interpolated to ~5500


def test_routes_ok_filters_to_status_ok_only():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-03-15", 5300.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    ok = dataset.routes_ok()
    assert (ok["status"] == STATUS_OK).all()
    assert ok["route_index"].notna().all()
    assert len(ok) < len(dataset.routes)  # Feb (no data) was excluded


# --- quality/provenance preservation -----------------------------------------


def test_quality_flags_are_preserved_on_the_national_row():
    """Route composition changes (INSUFFICIENT_DATA one month, OK the
    next) trigger a quality flag inside index_engine; this layer must
    surface it, not silently swallow it."""
    rows = (
        _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
        + _route_rows("BLR", "DEL", "2026-02-15", 5100.0, n=2)  # below min_observations
        + _route_rows("BLR", "DEL", "2026-03-15", 5500.0, n=5)
    )
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    march_row = dataset.national[dataset.national["period"] == "2026-03"].iloc[0]
    assert march_row["quality_flags"] is not None
    assert "composition" in march_row["quality_flags"]


def test_observations_used_is_attached_per_route():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0, n=7)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01"])
    row = dataset.route_series("BLR-DEL").iloc[0]
    assert row["observations_used"] == 7


# --- errors --------------------------------------------------------------------


def test_raises_value_error_when_no_periods_can_be_derived():
    with pytest.raises(ValueError):
        build_forecasting_dataset(pd.DataFrame(columns=["flight_date"]), base_period="2026-01")


def test_insufficient_data_error_propagates_not_swallowed():
    rows = [make_observation(total_fare=-1) for _ in range(5)]  # all invalid
    with pytest.raises(InsufficientDataError):
        build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01"])


def test_explicit_periods_argument_is_respected_over_derived_ones():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01", "2026-06"])
    assert list(dataset.national["period"]) == ["2026-01", "2026-06"]


# --- date sanity bounds (Stage 3.1 requirement 2) ------------------------------


def test_derive_calendar_periods_excludes_out_of_range_future_dates():
    """A malformed/typo'd date (e.g. year 2099) must not be allowed to
    expand the derived range to decades of spurious periods."""
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2099-05-15", 6000.0)
    reference = pd.Timestamp("2026-06-01")
    with pytest.warns(UserWarning, match="excluded"):
        periods = derive_calendar_periods(to_df(rows), reference_date=reference)
    # The 2099 row is excluded; range stays anchored to the legitimate January data only.
    assert periods == ["2026-01"]
    assert "2099-01" not in periods


def test_derive_calendar_periods_includes_a_valid_recent_date_without_warning():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2026-03-15", 6000.0)
    reference = pd.Timestamp("2026-06-01")
    import warnings as _warnings

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")  # any warning here would fail the test
        periods = derive_calendar_periods(to_df(rows), reference_date=reference)
    assert periods == ["2026-01", "2026-02", "2026-03"]


def test_derive_calendar_periods_reference_date_is_explicit_not_hardcoded_now():
    """The same malformed-looking date can be valid or invalid depending
    entirely on the explicitly-supplied reference_date — never on the
    real current date, so this test can never go stale."""
    rows = _route_rows("BLR", "DEL", "2030-01-15", 5000.0)
    # Relative to a reference far in the future, 2030 is unremarkable.
    periods_ok = derive_calendar_periods(to_df(rows), reference_date=pd.Timestamp("2029-06-01"))
    assert periods_ok == ["2030-01"]
    # Relative to a reference anchored at "today" in this test suite's own
    # world (2026), 2030 is far enough out to be excluded by the default bound.
    with pytest.warns(UserWarning):
        periods_excluded = derive_calendar_periods(to_df(rows), reference_date=pd.Timestamp("2026-06-01"))
    assert periods_excluded == []


def test_build_forecasting_dataset_records_date_sanity_warning_in_dataset_warnings():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0) + _route_rows("BLR", "DEL", "2099-05-15", 6000.0)
    dataset = build_forecasting_dataset(to_df(rows), base_period="2026-01")
    assert any("out-of-sanity-bound" in w for w in dataset.warnings)


# --- explicit period-list validation (Stage 3.1 requirement 4) ----------------


def test_build_forecasting_dataset_rejects_duplicate_explicit_periods():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
    with pytest.raises(ValueError, match="Duplicate"):
        build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01", "2026-01"])


def test_build_forecasting_dataset_rejects_malformed_explicit_periods():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
    with pytest.raises(ValueError, match="Malformed"):
        build_forecasting_dataset(to_df(rows), base_period="2026-01", periods=["2026-01", "not-a-period"])


def test_build_forecasting_dataset_normalizes_unsorted_explicit_periods():
    rows = _route_rows("BLR", "DEL", "2026-01-15", 5000.0)
    dataset = build_forecasting_dataset(
        to_df(rows), base_period="2026-01", periods=["2026-03", "2026-01", "2026-02"]
    )
    assert dataset.periods == ["2026-01", "2026-02", "2026-03"]
    assert list(dataset.national["period"]) == ["2026-01", "2026-02", "2026-03"]
