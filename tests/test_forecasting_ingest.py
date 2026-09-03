"""Tests for forecasting.ingest — the scraper-output -> ForecastingDataset
adapter. All fixtures here are hand-written, clearly-synthetic JSONL files
(never real Downloads/API data) mimicking scraper.storage's on-disk shape.
"""

import json

import pytest

from conftest import make_observation
from forecasting.ingest import (
    ScraperIngestResult,
    build_dataset_from_scraper_output,
    load_scraper_jsonl,
)
from forecasting.national import evaluate_national_baselines, forecast_national_index


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")
    return path


def _route_rows(flight_date, fare, n=5, **overrides):
    return [
        make_observation(flight_date=flight_date, total_fare=fare + i, **overrides)
        for i in range(n)
    ]


# --- load_scraper_jsonl -------------------------------------------------


def test_load_scraper_jsonl_reads_one_record_per_line(tmp_path):
    records = _route_rows("2026-01-15", 5000.0, n=3)
    path = _write_jsonl(tmp_path / "run_1.jsonl", records)
    loaded = load_scraper_jsonl(path)
    assert len(loaded) == 3
    assert loaded[0]["observation_id"] == records[0]["observation_id"]


def test_load_scraper_jsonl_accepts_multiple_paths(tmp_path):
    path_a = _write_jsonl(tmp_path / "a.jsonl", _route_rows("2026-01-15", 5000.0, n=2))
    path_b = _write_jsonl(tmp_path / "b.jsonl", _route_rows("2026-02-15", 5100.0, n=2))
    loaded = load_scraper_jsonl([path_a, path_b])
    assert len(loaded) == 4


def test_load_scraper_jsonl_skips_blank_lines(tmp_path):
    path = tmp_path / "with_blanks.jsonl"
    row = make_observation(flight_date="2026-01-15")
    path.write_text(f"\n{json.dumps(row)}\n\n", encoding="utf-8")
    loaded = load_scraper_jsonl(path)
    assert len(loaded) == 1


# --- build_dataset_from_scraper_output: real data ------------------------


def test_all_real_data_produces_dataset_and_is_not_flagged_synthetic(tmp_path):
    records = _route_rows("2026-01-15", 5000.0, n=5) + _route_rows("2026-02-15", 5100.0, n=5)
    path = _write_jsonl(tmp_path / "run_real.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")

    assert isinstance(result, ScraperIngestResult)
    assert result.total_records_loaded == 10
    assert result.real_record_count == 10
    assert result.synthetic_record_count == 0
    assert result.is_synthetic_data is False
    assert result.is_mixed_data is False
    assert result.skipped_malformed_count == 0
    assert list(result.dataset.national["period"]) == ["2026-01", "2026-02"]


def test_reuses_build_forecasting_dataset_numbers_unchanged(tmp_path):
    """Same fixture shape as test_forecasting_data_access.py's known-value
    check — confirms this adapter does not alter index_engine's numbers."""
    records = _route_rows("2026-01-15", 5000.0, n=5) + _route_rows("2026-08-15", 5500.0, n=5)
    path = _write_jsonl(tmp_path / "run_real.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")
    route = result.dataset.route_series("BLR-DEL", ok_only=True)
    aug = route[route["period"] == "2026-08"].iloc[0]
    assert abs(aug["route_index"] - 110.0) < 0.5


# --- synthetic / mock handling --------------------------------------------


def test_all_synthetic_data_is_flagged_and_warned(tmp_path):
    records = _route_rows("2026-01-15", 5000.0, n=5, is_mock=True)
    path = _write_jsonl(tmp_path / "run_mock.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")

    assert result.real_record_count == 0
    assert result.synthetic_record_count == 5
    assert result.is_synthetic_data is True
    assert result.is_mixed_data is False
    assert any("synthetic" in w.lower() for w in result.warnings)
    assert any("synthetic" in w.lower() for w in result.dataset.warnings)


def test_mixed_real_and_synthetic_without_allow_mock_raises(tmp_path):
    records = _route_rows("2026-01-15", 5000.0, n=3) + _route_rows(
        "2026-01-15", 5000.0, n=3, is_mock=True
    )
    path = _write_jsonl(tmp_path / "run_mixed.jsonl", records)

    with pytest.raises(ValueError, match="mixes"):
        build_dataset_from_scraper_output(path, base_period="2026-01")


def test_mixed_real_and_synthetic_with_allow_mock_succeeds_and_warns(tmp_path):
    records = _route_rows("2026-01-15", 5000.0, n=3) + _route_rows(
        "2026-01-15", 5000.0, n=3, is_mock=True
    )
    path = _write_jsonl(tmp_path / "run_mixed.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01", allow_mock=True)

    assert result.is_mixed_data is True
    assert result.real_record_count == 3
    assert result.synthetic_record_count == 3
    assert any("mixes" in w.lower() for w in result.warnings)


# --- structurally invalid rows ---------------------------------------------


def test_records_missing_required_fields_are_dropped_and_counted(tmp_path):
    good = _route_rows("2026-01-15", 5000.0, n=4)
    bad = [make_observation(flight_date="2026-01-15")]
    del bad[0]["airline"]  # missing a required field
    path = _write_jsonl(tmp_path / "run_partial.jsonl", good + bad)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")

    assert result.total_records_loaded == 5
    assert result.skipped_malformed_count == 1
    assert result.real_record_count == 4
    assert any("dropped" in w.lower() for w in result.warnings)


def test_records_with_non_positive_fare_are_dropped(tmp_path):
    good = _route_rows("2026-01-15", 5000.0, n=4)
    bad = [make_observation(flight_date="2026-01-15", total_fare=0.0)]
    path = _write_jsonl(tmp_path / "run_bad_fare.jsonl", good + bad)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")

    assert result.skipped_malformed_count == 1
    assert result.real_record_count == 4


def test_all_records_invalid_raises(tmp_path):
    bad = [make_observation(flight_date="2026-01-15", total_fare=-1.0)]
    path = _write_jsonl(tmp_path / "run_all_bad.jsonl", bad)

    with pytest.raises(ValueError, match="No structurally-usable"):
        build_dataset_from_scraper_output(path, base_period="2026-01")


# --- calendar-gap / contiguity safeguards preserved -------------------------


def test_gap_month_still_produces_a_row_not_a_silent_drop(tmp_path):
    """Same guarantee as data_access.py's own test: a route with no data
    in an intermediate month still gets a row, never vanishes."""
    records = _route_rows("2026-01-15", 5000.0, n=5) + _route_rows("2026-03-15", 5300.0, n=5)
    path = _write_jsonl(tmp_path / "run_gap.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")
    series = result.dataset.route_series("BLR-DEL")
    assert list(series["period"]) == ["2026-01", "2026-02", "2026-03"]


# --- end-to-end: ingest -> forecasting -------------------------------------


def test_ingested_dataset_feeds_forecast_national_index(tmp_path):
    records = _route_rows("2026-01-15", 5000.0, n=5, is_mock=True) + _route_rows(
        "2026-02-15", 5100.0, n=5, is_mock=True
    )
    path = _write_jsonl(tmp_path / "run_mock.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")
    assert result.is_synthetic_data is True

    forecast = forecast_national_index(result.dataset, is_synthetic_data=result.is_synthetic_data)
    assert forecast is not None


def test_ingested_dataset_feeds_evaluate_national_baselines(tmp_path):
    records = (
        _route_rows("2026-01-15", 5000.0, n=5, is_mock=True)
        + _route_rows("2026-02-15", 5100.0, n=5, is_mock=True)
        + _route_rows("2026-03-15", 5200.0, n=5, is_mock=True)
    )
    path = _write_jsonl(tmp_path / "run_mock.jsonl", records)

    result = build_dataset_from_scraper_output(path, base_period="2026-01")
    evaluations = evaluate_national_baselines(result.dataset, is_synthetic_data=result.is_synthetic_data)
    assert evaluations is not None
