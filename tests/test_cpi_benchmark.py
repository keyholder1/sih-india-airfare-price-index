import math
from pathlib import Path

import pandas as pd
import pytest

from conftest import make_observation, to_df
from forecasting import (
    ForecastingDataset,
    MospiCpiSeries,
    build_forecasting_dataset,
    compare_to_mospi_cpi,
    load_mospi_cpi_series,
)
from forecasting.cpi_results import STATUS_INSUFFICIENT_DATA, STATUS_INSUFFICIENT_OVERLAP, STATUS_OK
from forecasting.data_access import NATIONAL_COLUMNS, ROUTE_COLUMNS
from index_engine.utils import shift_period

CPI_XLSX_PATH = Path(__file__).parent.parent / "data" / "benchmarks" / "cpi_1337.xlsx"


def _empty_dataset(national_rows=None) -> ForecastingDataset:
    national_df = pd.DataFrame(national_rows or [], columns=NATIONAL_COLUMNS)
    routes_df = pd.DataFrame([], columns=ROUTE_COLUMNS)
    periods = [r["period"] for r in (national_rows or [])]
    return ForecastingDataset(base_period="2026-01", periods=periods, national=national_df, routes=routes_df)


def _national_row(period, national_index, coverage_rate=1.0):
    row = {c: None for c in NATIONAL_COLUMNS}
    row["period"] = period
    row["national_index"] = national_index
    row["coverage_rate"] = coverage_rate
    return row


def _mospi_fixture(index_by_period, yoy=None, imputed=None, base_year=2024):
    periods = sorted(index_by_period.keys())
    return MospiCpiSeries(
        periods=periods,
        index_by_period=index_by_period,
        yoy_inflation_by_period=yoy or {p: None for p in periods},
        imputed_by_period=imputed or {p: False for p in periods},
        base_year=base_year,
        item="Airfare",
        state="All India",
        sector="Combined",
        source_file="fixture",
    )


# --- cpi_loader: parsing correctness against the real file --------------------


def test_load_mospi_cpi_series_matches_hand_verified_yoy_values():
    """Regression anchor against the real file: recompute (index_t /
    index_t-12yrs_within_extract - 1) * 100 and confirm it matches
    MoSPI's own published `inflation` column exactly."""
    mospi = load_mospi_cpi_series(CPI_XLSX_PATH)

    assert mospi.base_year == 2024
    assert len(mospi.periods) == 19
    assert mospi.periods[0] == "2025-01"
    assert mospi.periods[-1] == "2026-07"

    assert mospi.index_by_period["2026-01"] == pytest.approx(122.71)
    assert mospi.yoy_inflation_by_period["2026-01"] == pytest.approx(6.65)
    assert mospi.index_by_period["2025-01"] == pytest.approx(115.05)
    # Hand-verified: 122.71 / 115.05 = 1.0666 -> +6.66% (matches published 6.65% within rounding)
    recomputed = (mospi.index_by_period["2026-01"] / mospi.index_by_period["2025-01"] - 1.0) * 100.0
    assert recomputed == pytest.approx(mospi.yoy_inflation_by_period["2026-01"], abs=0.02)

    assert mospi.index_by_period["2026-02"] == pytest.approx(122.43)
    assert mospi.yoy_inflation_by_period["2026-02"] == pytest.approx(-7.01)
    assert mospi.index_by_period["2025-02"] == pytest.approx(131.66)

    # 2025 months have no 12-months-prior data within this extract -> None, not fabricated.
    assert mospi.yoy_inflation_by_period["2025-01"] is None
    assert mospi.yoy_inflation_by_period["2025-12"] is None


def test_load_mospi_cpi_series_imputation_flag_parsed():
    mospi = load_mospi_cpi_series(CPI_XLSX_PATH)
    # Every row in this extract is "N" (not imputed).
    assert all(not imputed for imputed in mospi.imputed_by_period.values())


def test_load_mospi_cpi_series_raises_on_missing_columns():
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        pd.DataFrame({"year": [2026], "month": ["January"]}).to_excel(f.name, index=False)
        with pytest.raises(ValueError, match="missing required column"):
            load_mospi_cpi_series(f.name)


def test_load_mospi_cpi_series_raises_on_unrecognized_month():
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        pd.DataFrame(
            {
                "year": [2026], "month": ["Smarch"], "index": [100.0], "inflation": [None],
                "imputation": ["N"], "base_year": [2024],
            }
        ).to_excel(f.name, index=False)
        with pytest.raises(ValueError, match="unrecognized month"):
            load_mospi_cpi_series(f.name)


# --- rebasing -------------------------------------------------------------------


def test_rebase_produces_hand_computed_values():
    from forecasting.cpi_benchmark import _rebase

    series = pd.Series([200.0, 220.0, 240.0], index=["2026-01", "2026-02", "2026-03"])
    rebased = _rebase(series, "2026-01")
    assert rebased["2026-01"] == pytest.approx(100.0)
    assert rebased["2026-02"] == pytest.approx(110.0)  # 220/200*100
    assert rebased["2026-03"] == pytest.approx(120.0)  # 240/200*100


# --- overlap detection ------------------------------------------------------------


def test_insufficient_overlap_when_no_shared_period():
    dataset = _empty_dataset([_national_row("2026-01", 100.0)])
    mospi = _mospi_fixture({"2020-01": 90.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.status == STATUS_INSUFFICIENT_OVERLAP
    assert result.overlap_period_count == 0
    assert result.comparisons == []
    assert result.mean_absolute_mom_difference_pct_points is None
    assert result.mom_correlation is None


def test_overlap_excludes_periods_missing_on_either_side():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 105.0), _national_row("2026-03", 110.0)]
    )
    mospi = _mospi_fixture({"2026-02": 120.0, "2026-03": 121.0, "2026-04": 122.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    # Only 2026-02 and 2026-03 exist on both sides.
    assert result.overlap_start == "2026-02"
    assert result.overlap_end == "2026-03"
    assert result.overlap_period_count == 2


def test_national_index_missing_period_within_range_is_excluded_not_interpolated():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", None), _national_row("2026-03", 110.0)]
    )
    mospi = _mospi_fixture({"2026-01": 120.0, "2026-02": 121.0, "2026-03": 122.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    periods_compared = [c.period for c in result.comparisons]
    assert "2026-02" not in periods_compared  # missing on our side -> excluded, never filled
    assert periods_compared == ["2026-01", "2026-03"]


# --- rebased level values in comparisons -----------------------------------------


def test_comparison_rebases_both_sides_to_first_overlap_period():
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 110.0)])
    mospi = _mospi_fixture({"2026-01": 200.0, "2026-02": 210.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    first = next(c for c in result.comparisons if c.period == "2026-01")
    assert first.our_index_rebased == pytest.approx(100.0)
    assert first.mospi_index_rebased == pytest.approx(100.0)
    second = next(c for c in result.comparisons if c.period == "2026-02")
    assert second.our_index_rebased == pytest.approx(110.0)  # 110/100*100
    assert second.mospi_index_rebased == pytest.approx(105.0)  # 210/200*100


# --- MoM difference and minimum-pair gating --------------------------------------


def test_mom_difference_computed_between_calendar_adjacent_periods():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 110.0), _national_row("2026-03", 121.0)]
    )
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0, "2026-03": 110.25})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    feb = next(c for c in result.comparisons if c.period == "2026-02")
    assert feb.our_mom_pct == pytest.approx(10.0)
    assert feb.mospi_mom_pct == pytest.approx(5.0)
    assert feb.mom_difference_pct_points == pytest.approx(5.0)


def test_mom_not_computed_across_a_gap_in_the_overlap():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-03", 121.0)]  # Feb missing entirely from periods
    )
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-03": 110.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    march = next(c for c in result.comparisons if c.period == "2026-03")
    # Jan and Mar are NOT calendar-adjacent (Feb between them) -> no MoM computed.
    assert march.our_mom_pct is None
    assert march.mospi_mom_pct is None


def test_mean_absolute_difference_none_below_minimum_pairs():
    # Only 2 overlapping levels -> 1 MoM pair -> below MIN_PAIRS_FOR_MEAN_ABS_DIFF (2).
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 110.0)])
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.mean_absolute_mom_difference_pct_points is None


def test_mean_absolute_difference_reported_at_minimum_pairs():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 110.0), _national_row("2026-03", 121.0)]
    )
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0, "2026-03": 110.25})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    # feb diff = 10-5=5, mar diff = (121/110-1)*100=10 vs (110.25/105-1)*100=5 -> diff=5
    assert result.mean_absolute_mom_difference_pct_points == pytest.approx(5.0)


def test_correlation_none_below_minimum_pairs():
    rows = [_national_row(f"2026-0{i+1}", 100.0 * (1.02**i)) for i in range(4)]  # 4 levels -> 3 MoM pairs
    dataset = _empty_dataset(rows)
    mospi = _mospi_fixture({f"2026-0{i+1}": 100.0 * (1.01**i) for i in range(4)})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.mom_correlation is None
    assert result.mom_correlation_status == STATUS_INSUFFICIENT_DATA


def test_correlation_reported_at_minimum_pairs_with_illustrative_note():
    # Deliberately varying (not pure exponential) growth so MoM% has real
    # variance in both series — a perfectly constant growth rate has zero
    # variance and correlation is correctly undefined (see the
    # zero-variance guard in _pearson_correlation).
    our_values = [100.0, 102.0, 107.0, 105.0, 111.0]  # 4 varying MoM moves
    mospi_values = [100.0, 101.0, 104.0, 103.0, 106.0]
    rows = [_national_row(f"2026-0{i+1}", v) for i, v in enumerate(our_values)]
    dataset = _empty_dataset(rows)
    mospi = _mospi_fixture({f"2026-0{i+1}": v for i, v in enumerate(mospi_values)})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.mom_correlation is not None
    assert result.mom_correlation_status == STATUS_OK
    assert "illustrative only" in result.notes


# --- MoSPI imputation handling ----------------------------------------------------


def test_mospi_imputed_period_excluded_from_metrics_by_default():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 110.0), _national_row("2026-03", 121.0)]
    )
    mospi = _mospi_fixture(
        {"2026-01": 100.0, "2026-02": 105.0, "2026-03": 110.25},
        imputed={"2026-01": False, "2026-02": True, "2026-03": False},  # Feb imputed
    )
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    feb = next(c for c in result.comparisons if c.period == "2026-02")
    assert feb.mospi_imputed is True
    assert feb.included_in_metrics is False
    assert feb.exclusion_reason is not None
    # Its level is still reported (transparency), but no MoM was computed off it in either direction.
    assert feb.our_index_rebased is not None
    mar = next(c for c in result.comparisons if c.period == "2026-03")
    assert mar.our_mom_pct is None  # blocked because the preceding period (Feb) was excluded


def test_mospi_imputed_period_included_when_flag_disabled():
    dataset = _empty_dataset(
        [_national_row("2026-01", 100.0), _national_row("2026-02", 110.0), _national_row("2026-03", 121.0)]
    )
    mospi = _mospi_fixture(
        {"2026-01": 100.0, "2026-02": 105.0, "2026-03": 110.25},
        imputed={"2026-01": False, "2026-02": True, "2026-03": False},
    )
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True, exclude_mospi_imputed=False)
    feb = next(c for c in result.comparisons if c.period == "2026-02")
    assert feb.included_in_metrics is True
    mar = next(c for c in result.comparisons if c.period == "2026-03")
    assert mar.our_mom_pct is not None  # no longer blocked


# --- synthetic-data labeling -------------------------------------------------------


def test_is_synthetic_airfare_data_is_explicit_parameter_not_defaulted():
    """compare_to_mospi_cpi must not have a default for this parameter —
    calling without it should raise a TypeError, not silently assume."""
    import inspect

    sig = inspect.signature(compare_to_mospi_cpi)
    assert sig.parameters["is_synthetic_airfare_data"].default is inspect.Parameter.empty


def test_synthetic_flag_propagates_and_note_present_when_true():
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 110.0)])
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.is_synthetic_airfare_data is True
    assert "SYNTHETIC" in result.notes


def test_synthetic_flag_false_when_explicitly_passed_false():
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 110.0)])
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=False)
    assert result.is_synthetic_airfare_data is False
    assert "SYNTHETIC" not in result.notes


# --- min_coverage_rate passthrough -------------------------------------------------


def test_min_coverage_rate_excludes_low_quality_periods_from_overlap():
    dataset = _empty_dataset(
        [
            _national_row("2026-01", 100.0, coverage_rate=1.0),
            _national_row("2026-02", 999.0, coverage_rate=0.05),  # low quality
        ]
    )
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0})
    filtered = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True, min_coverage_rate=0.5)
    unfiltered = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True, min_coverage_rate=None)
    assert filtered.overlap_period_count == 1
    assert unfiltered.overlap_period_count == 2


# --- serialization ------------------------------------------------------------------


def test_result_to_dict_is_json_serializable_shape():
    dataset = _empty_dataset([_national_row("2026-01", 100.0), _national_row("2026-02", 110.0)])
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    d = result.to_dict()
    assert d["status"] == STATUS_OK
    assert isinstance(d["comparisons"], list)
    assert isinstance(d["comparisons"][0], dict)
    assert "period" in d["comparisons"][0]


# --- yoy comparison: real logic (Stage 4) --------------------------------------------


def _monthly_rows(start_period, count, values, coverage_rate=1.0):
    """count national rows starting at start_period, one per consecutive
    calendar month, with the given values list (len must == count)."""
    periods = [start_period if i == 0 else shift_period(start_period, i) for i in range(count)]
    return [_national_row(p, v, coverage_rate=coverage_rate) for p, v in zip(periods, values)]


def _mospi_monthly(start_period, count, values, imputed=None):
    periods = [start_period if i == 0 else shift_period(start_period, i) for i in range(count)]
    index_by_period = dict(zip(periods, values))
    imputed_by_period = imputed or {p: False for p in periods}
    return _mospi_fixture(index_by_period, imputed=imputed_by_period)


def test_yoy_insufficient_data_with_less_than_12_months_history():
    """Two months of history can never contain a 12-months-apart pair —
    genuinely insufficient, not a stub. This must hold even when an
    incidental (unused-by-this-logic) yoy_change_pct field is present on
    a row, since this module computes YoY itself from index values, not
    from that field."""
    row = _national_row("2026-01", 100.0)
    row["yoy_change_pct"] = 5.5  # incidental field, not used by compare_to_mospi_cpi's own YoY math
    dataset = _empty_dataset([row, _national_row("2026-02", 110.0)])
    mospi = _mospi_fixture({"2026-01": 100.0, "2026-02": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.yoy_comparison_status == STATUS_INSUFFICIENT_DATA
    assert result.yoy_period_count == 0
    assert result.mean_absolute_yoy_difference_pct_points is None
    assert all(c.our_yoy_pct is None for c in result.comparisons)


def test_yoy_computed_at_exactly_12_months_separation():
    """Boundary case: exactly one pair, 12 calendar months apart, both
    sides present -> a real YoY value, hand-computed exactly."""
    dataset = _empty_dataset([_national_row("2025-01", 100.0), _national_row("2026-01", 110.0)])
    mospi = _mospi_fixture({"2025-01": 100.0, "2026-01": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)

    assert result.yoy_comparison_status == STATUS_OK
    assert result.yoy_period_count == 1
    jan2026 = next(c for c in result.comparisons if c.period == "2026-01")
    assert jan2026.our_yoy_pct == pytest.approx(10.0)  # (110/100 - 1) * 100, rebased to 2025-01
    assert jan2026.mospi_yoy_pct == pytest.approx(5.0)  # (105/100 - 1) * 100
    assert jan2026.yoy_difference_pct_points == pytest.approx(5.0)
    jan2025 = next(c for c in result.comparisons if c.period == "2025-01")
    assert jan2025.our_yoy_pct is None  # no prior period 12 months before 2025-01 in this fixture


def test_yoy_multiple_valid_periods_with_24_months_of_data():
    """24 consecutive months on both sides -> 12 valid YoY pairs (every
    month from month 13 onward has a real 12-months-prior counterpart),
    and the mean-absolute-difference summary is populated once >= 2
    pairs exist."""
    our_values = [100.0 + i for i in range(24)]
    mospi_values = [100.0 + 0.5 * i for i in range(24)]
    dataset = _empty_dataset(_monthly_rows("2024-01", 24, our_values))
    mospi = _mospi_monthly("2024-01", 24, mospi_values)
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)

    assert result.yoy_comparison_status == STATUS_OK
    assert result.yoy_period_count == 12
    assert result.mean_absolute_yoy_difference_pct_points is not None
    assert all(
        c.our_yoy_pct is not None for c in result.comparisons if c.period >= "2025-01"
    )


def test_yoy_not_computed_across_a_missing_calendar_period():
    """2025-01 is missing entirely (a genuine calendar gap). 2026-01's
    would-be 12-months-prior period (2025-01) therefore isn't in the
    overlap at all -> no YoY for 2026-01, not fabricated. 2026-02's prior
    (2025-02) IS present, so that pair still computes -> the gap only
    breaks the one pair it actually affects."""
    our_periods_values = {shift_period("2025-01", i): 100.0 + i for i in range(1, 12)}  # 2025-02..2025-12
    our_periods_values["2026-01"] = 200.0
    our_periods_values["2026-02"] = 201.0
    rows = [_national_row(p, v) for p, v in sorted(our_periods_values.items())]
    dataset = _empty_dataset(rows)
    mospi = _mospi_fixture({p: v * 0.9 for p, v in our_periods_values.items()})

    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)

    jan2026 = next(c for c in result.comparisons if c.period == "2026-01")
    assert jan2026.our_yoy_pct is None  # 2025-01 missing entirely -> no prior to compare against
    feb2026 = next(c for c in result.comparisons if c.period == "2026-02")
    assert feb2026.our_yoy_pct is not None  # 2025-02 present -> this pair is unaffected by the gap


def test_yoy_not_computed_for_mismatched_overlap_period():
    """Distinct from a missing-period gap: 2025-01 IS present on both
    sides (so it individually looks fine), but MoSPI flags it as imputed
    and the default exclude_mospi_imputed=True marks it
    included_in_metrics=False. 2026-01's YoY pair is therefore excluded
    -- not because the period is absent, but because it's untrustworthy
    for comparison purposes. This must be a distinct code path from the
    missing-period case, not silently merged with it."""
    periods_values = {shift_period("2025-01", i): 100.0 + i for i in range(13)}  # 2025-01..2026-01
    rows = [_national_row(p, v) for p, v in sorted(periods_values.items())]
    dataset = _empty_dataset(rows)
    imputed = {p: (p == "2025-01") for p in periods_values}
    mospi = _mospi_fixture({p: v * 0.9 for p, v in periods_values.items()}, imputed=imputed)

    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)

    jan2025 = next(c for c in result.comparisons if c.period == "2025-01")
    assert jan2025.mospi_imputed is True
    assert jan2025.included_in_metrics is False
    # 2025-01 is present in the overlap (unlike the missing-period test) ...
    periods_compared = [c.period for c in result.comparisons]
    assert "2025-01" in periods_compared
    # ... but 2026-01's YoY pair is still excluded, because its prior is untrustworthy, not absent.
    jan2026 = next(c for c in result.comparisons if c.period == "2026-01")
    assert jan2026.our_yoy_pct is None


def test_yoy_synthetic_flag_and_small_sample_note_present():
    dataset = _empty_dataset([_national_row("2025-01", 100.0), _national_row("2026-01", 110.0)])
    mospi = _mospi_fixture({"2025-01": 100.0, "2026-01": 105.0})
    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)
    assert result.is_synthetic_airfare_data is True
    assert "SYNTHETIC" in result.notes
    # Only 1 YoY pair -> below MIN_PAIRS_FOR_MEAN_ABS_YOY_DIFF -> illustrative-sample note expected.
    assert "aligned 12-months-apart period" in result.notes


# --- real-file integration test ------------------------------------------------------


def test_real_cpi_file_and_real_sample_fares_integration():
    """End-to-end against the REAL cpi_1337.xlsx and the repo's REAL
    sample_fares.csv. Asserts STRUCTURE (the expected 7-month overlap,
    Jan-Jul 2026) — never asserts on the synthetic numeric metric values,
    since those reflect a fabricated random-walk series and are not
    evidence of anything about real-world tracking accuracy."""
    fares = to_df(
        [
            make_observation(
                flight_date=f"2026-0{month}-15",
                booking_date=f"2026-0{month}-05",
                total_fare=5000.0 + month * 100 + i,
            )
            for month in range(1, 9)  # Jan-Aug 2026, matching sample_fares.csv's real range
            for i in range(5)
        ]
    )
    dataset = build_forecasting_dataset(fares, base_period="2026-01")
    mospi = load_mospi_cpi_series(CPI_XLSX_PATH)

    result = compare_to_mospi_cpi(dataset, mospi, is_synthetic_airfare_data=True)

    assert result.status == STATUS_OK
    assert result.overlap_start == "2026-01"
    assert result.overlap_end == "2026-07"
    assert result.overlap_period_count == 7  # Jan-Jul 2026: our Aug has no MoSPI counterpart yet
    assert result.is_synthetic_airfare_data is True
    assert "SYNTHETIC" in result.notes
    # Structural checks only — no assertion on mean_absolute_mom_difference_pct_points
    # or mom_correlation's actual VALUE, since that would treat a fabricated
    # series' relationship to real MoSPI data as if it meant something.
    assert result.mospi_base_year == 2024
