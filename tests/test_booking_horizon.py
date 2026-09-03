"""Tests for forecasting.booking_horizon. All fixtures here are hand-written,
clearly-synthetic records (never real Downloads/API data) mimicking
scraper.storage's on-disk JSONL shape, same convention as
test_forecasting_ingest.py.
"""

import json

import pytest

from conftest import make_observation
from forecasting.booking_horizon import (
    BOOKING_WINDOWS,
    BookingHorizonAnalysis,
    BookingHorizonPartition,
    NO_DATA,
    build_booking_horizon_datasets,
    classify_booking_window,
    compute_advance_purchase_days,
    partition_by_booking_window,
)
from forecasting.results import STATUS_INSUFFICIENT_DATA, STATUS_OK


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")
    return path


def _window_rows(flight_date, booking_date, fare, n=5, **overrides):
    return [
        make_observation(flight_date=flight_date, booking_date=booking_date, total_fare=fare + i, **overrides)
        for i in range(n)
    ]


# --- compute_advance_purchase_days ----------------------------------------


def test_compute_advance_purchase_days_normal():
    days = compute_advance_purchase_days({"flight_date": "2026-01-15", "booking_date": "2026-01-01"})
    assert days == 14


def test_compute_advance_purchase_days_missing_flight_date():
    assert compute_advance_purchase_days({"booking_date": "2026-01-01"}) is None


def test_compute_advance_purchase_days_missing_booking_date():
    assert compute_advance_purchase_days({"flight_date": "2026-01-15"}) is None


def test_compute_advance_purchase_days_unparseable_date():
    assert compute_advance_purchase_days({"flight_date": "not-a-date", "booking_date": "2026-01-01"}) is None


def test_compute_advance_purchase_days_negative_when_booking_after_flight():
    days = compute_advance_purchase_days({"flight_date": "2026-01-01", "booking_date": "2026-01-15"})
    assert days == -14


# --- classify_booking_window: boundaries -----------------------------------


@pytest.mark.parametrize(
    "days,expected",
    [
        (1, "T1_7"),
        (7, "T1_7"),
        (8, "T8_14"),
        (14, "T8_14"),
        (15, "T15_21"),
        (21, "T15_21"),
        (22, "T22_30"),
        (30, "T22_30"),
        (31, "T31_45"),
        (45, "T31_45"),
    ],
)
def test_classify_booking_window_boundaries(days, expected):
    assert classify_booking_window(days) == expected


@pytest.mark.parametrize("days", [0, 46, 100, -1, -14])
def test_classify_booking_window_out_of_range_or_negative_returns_none(days):
    assert classify_booking_window(days) is None


def test_classify_booking_window_none_input_returns_none():
    assert classify_booking_window(None) is None


def test_booking_windows_cover_t1_through_t45_with_no_gaps_or_overlaps():
    covered = set()
    for w in BOOKING_WINDOWS:
        for d in range(w.min_days, w.max_days + 1):
            assert d not in covered, f"day {d} covered by more than one window"
            covered.add(d)
    assert covered == set(range(1, 46))


# --- partition_by_booking_window -------------------------------------------


def test_partition_splits_records_into_correct_windows():
    records = (
        _window_rows("2026-01-08", "2026-01-05", 6000.0, n=3)  # 3 days -> T1_7
        + _window_rows("2026-01-25", "2026-01-01", 5000.0, n=2)  # 24 days -> T22_30
    )
    partition = partition_by_booking_window(records)
    assert len(partition.window_records["T1_7"]) == 3
    assert len(partition.window_records["T22_30"]) == 2
    assert len(partition.window_records["T8_14"]) == 0
    assert partition.total_records == 5
    assert partition.missing_date_count == 0
    assert partition.invalid_date_count == 0
    assert partition.negative_horizon_count == 0
    assert partition.out_of_range_count == 0


def test_partition_counts_missing_dates():
    good = _window_rows("2026-01-08", "2026-01-05", 6000.0, n=2)
    missing = [make_observation(flight_date="2026-01-08")]
    del missing[0]["booking_date"]
    partition = partition_by_booking_window(good + missing)
    assert partition.missing_date_count == 1
    assert sum(len(v) for v in partition.window_records.values()) == 2


def test_partition_counts_negative_horizon_separately_from_out_of_range():
    same_day = _window_rows("2026-01-08", "2026-01-08", 5000.0, n=1)  # T+0, out of range
    booking_after_flight = _window_rows("2026-01-08", "2026-01-20", 5000.0, n=1)  # negative
    beyond_45 = _window_rows("2026-03-01", "2026-01-01", 5000.0, n=1)  # 59 days, out of range
    partition = partition_by_booking_window(same_day + booking_after_flight + beyond_45)
    assert partition.negative_horizon_count == 1
    assert partition.out_of_range_count == 2
    assert sum(len(v) for v in partition.window_records.values()) == 0


# --- build_booking_horizon_datasets: end-to-end ----------------------------


def test_two_windows_produce_distinct_datasets(tmp_path):
    # 3 days out -> T1_7, in both Jan and Feb periods.
    last_minute = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=5) + _window_rows(
        "2026-02-08", "2026-02-05", 8200.0, n=5
    )
    # 25 days out -> T22_30, in both Jan and Feb periods.
    advance = _window_rows("2026-01-08", "2025-12-14", 5000.0, n=5) + _window_rows(
        "2026-02-08", "2026-01-14", 5100.0, n=5
    )
    path = _write_jsonl(tmp_path / "run.jsonl", last_minute + advance)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01")

    assert isinstance(analysis, BookingHorizonAnalysis)
    t1_7 = analysis.windows["T1_7"]
    t22_30 = analysis.windows["T22_30"]
    assert t1_7.status == STATUS_OK
    assert t22_30.status == STATUS_OK
    assert t1_7.record_count == 10
    assert t22_30.record_count == 10
    # Different fare levels per window -> different national index history.
    t1_7_feb = t1_7.dataset.national[t1_7.dataset.national["period"] == "2026-02"].iloc[0]
    t22_30_feb = t22_30.dataset.national[t22_30.dataset.national["period"] == "2026-02"].iloc[0]
    assert t1_7_feb["national_index"] != t22_30_feb["national_index"]


def test_windows_with_no_records_get_no_data_status(tmp_path):
    records = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=5)  # only T1_7
    path = _write_jsonl(tmp_path / "run.jsonl", records)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01")

    assert analysis.windows["T1_7"].status == STATUS_OK
    for name in ("T8_14", "T15_21", "T22_30", "T31_45"):
        assert analysis.windows[name].status == NO_DATA
        assert analysis.windows[name].dataset is None
        assert analysis.windows[name].record_count == 0


def test_one_window_insufficient_data_does_not_block_others(tmp_path):
    # T1_7: legit, in-range dates -> should build OK.
    ok_window = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=5)
    # T8_14: flight_date far in the past -> no derivable periods -> this
    # window's build_forecasting_dataset call raises, caught as
    # STATUS_INSUFFICIENT_DATA, without affecting T1_7.
    far_past = _window_rows("2015-01-15", "2015-01-01", 5000.0, n=5)
    path = _write_jsonl(tmp_path / "run.jsonl", ok_window + far_past)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01")

    assert analysis.windows["T1_7"].status == STATUS_OK
    assert analysis.windows["T8_14"].status == STATUS_INSUFFICIENT_DATA
    assert analysis.windows["T8_14"].dataset is None
    assert analysis.windows["T8_14"].error is not None


def test_record_missing_booking_date_is_dropped_upstream_of_partitioning(tmp_path):
    """booking_date/flight_date are both data-contract-required fields, so
    a record missing either is already dropped by the same structural
    filter ingest.py uses, before it ever reaches partitioning -- it shows
    up as skipped_malformed, not partition.missing_date_count (which is
    reachable only via partition_by_booking_window called directly, e.g.
    on already-structurally-usable records with a present-but-unparseable
    date -- see test_partition_counts_missing_dates and
    test_record_with_unparseable_date_is_excluded_end_to_end below)."""
    good = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=5)
    missing = [make_observation(flight_date="2026-01-08")]
    del missing[0]["booking_date"]
    path = _write_jsonl(tmp_path / "run.jsonl", good + missing)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01")

    assert analysis.total_records_loaded == 6
    assert analysis.skipped_malformed_count == 1
    assert analysis.partition.total_records == 5
    assert analysis.partition.missing_date_count == 0
    assert any("missing a required field" in w.lower() for w in analysis.warnings)


def test_record_with_unparseable_date_is_excluded_end_to_end(tmp_path):
    good = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=5)
    bad = [make_observation(flight_date="2026-01-08", booking_date="not-a-date")]
    path = _write_jsonl(tmp_path / "run.jsonl", good + bad)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01")

    # Passed the structural (non-empty) filter, so it reaches partitioning,
    # where the unparseable date is caught and counted -- not silently
    # dropped or misclassified into a window.
    assert analysis.skipped_malformed_count == 0
    assert analysis.partition.total_records == 6
    assert analysis.partition.invalid_date_count == 1
    assert any("unparseable" in w.lower() for w in analysis.warnings)


# --- synthetic / mock handling ----------------------------------------------


def test_all_synthetic_data_is_flagged(tmp_path):
    records = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=5, is_mock=True) + _window_rows(
        "2026-02-08", "2026-02-05", 8200.0, n=5, is_mock=True
    )
    path = _write_jsonl(tmp_path / "run.jsonl", records)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01")

    assert analysis.is_synthetic_data is True
    assert analysis.real_record_count == 0
    assert analysis.synthetic_record_count == 10
    assert any("synthetic" in w.lower() for w in analysis.warnings)


def test_mixed_real_and_synthetic_without_allow_mock_raises(tmp_path):
    real = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=3)
    mock = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=3, is_mock=True)
    path = _write_jsonl(tmp_path / "run.jsonl", real + mock)

    with pytest.raises(ValueError, match="mixes"):
        build_booking_horizon_datasets(path, base_period="2026-01")


def test_mixed_real_and_synthetic_with_allow_mock_succeeds(tmp_path):
    real = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=3)
    mock = _window_rows("2026-01-08", "2026-01-05", 8000.0, n=3, is_mock=True)
    path = _write_jsonl(tmp_path / "run.jsonl", real + mock)

    analysis = build_booking_horizon_datasets(path, base_period="2026-01", allow_mock=True)

    assert analysis.is_mixed_data is True
    assert analysis.real_record_count == 3
    assert analysis.synthetic_record_count == 3


def test_no_usable_records_raises(tmp_path):
    bad = [make_observation(flight_date="2026-01-08")]
    del bad[0]["airline"]
    path = _write_jsonl(tmp_path / "run.jsonl", bad)

    with pytest.raises(ValueError, match="No structurally-usable"):
        build_booking_horizon_datasets(path, base_period="2026-01")
