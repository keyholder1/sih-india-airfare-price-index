import pandas as pd

from conftest import make_observation, to_df
from index_engine import IndexConfig
from index_engine.cleaning import REASON_DUPLICATE, REASON_OUTLIER_IQR, clean_observations
from index_engine.normalization import enrich


def _enriched(rows, config):
    return enrich(to_df(rows), config)


def test_exact_duplicate_observation_id_is_removed():
    config = IndexConfig(base_period="2026-01")
    row = make_observation(observation_id="DUP1")
    df = _enriched([row, dict(row)], config)
    clean, report = clean_observations(df, config, total_input=len(df))
    assert len(clean) == 1
    assert report.removed_by_reason[REASON_DUPLICATE] == 1


def test_extreme_fare_flagged_as_outlier_iqr():
    config = IndexConfig(base_period="2026-01", outlier_method="iqr")
    normal_rows = [make_observation(total_fare=5000.0 + i * 10) for i in range(10)]
    outlier_row = make_observation(total_fare=100000.0)
    df = _enriched(normal_rows + [outlier_row], config)
    clean, report = clean_observations(df, config, total_input=len(df))
    assert len(clean) == 10
    assert report.removed_by_reason[REASON_OUTLIER_IQR] == 1
    assert not (clean["total_fare"] == 100000.0).any()


def test_outlier_rule_skips_groups_below_four_observations():
    """IQR/MAD/percentile are not meaningfully computable on very small
    samples, so groups of 3 or fewer are never outlier-flagged, however
    extreme a single value is — verified at exactly the n=3/n=4 boundary."""
    config = IndexConfig(base_period="2026-01", outlier_method="iqr")

    three_obs_with_extreme = [make_observation(total_fare=5000.0), make_observation(total_fare=5100.0), make_observation(total_fare=500000.0)]
    df = _enriched(three_obs_with_extreme, config)
    clean, report = clean_observations(df, config, total_input=len(df))
    assert len(clean) == 3  # extreme value NOT removed; group too small to test
    assert report.removed_by_reason == {}

    four_obs_with_extreme = three_obs_with_extreme + [make_observation(total_fare=5050.0)]
    df = _enriched(four_obs_with_extreme, config)
    clean, report = clean_observations(df, config, total_input=len(df))
    assert len(clean) == 3  # now large enough; the extreme value IS removed
    assert report.removed_by_reason.get("OUTLIER_IQR") == 1


def test_outlier_detection_can_be_disabled():
    config = IndexConfig(base_period="2026-01", outlier_method="none")
    normal_rows = [make_observation(total_fare=5000.0 + i * 10) for i in range(10)]
    outlier_row = make_observation(total_fare=100000.0)
    df = _enriched(normal_rows + [outlier_row], config)
    clean, report = clean_observations(df, config, total_input=len(df))
    assert len(clean) == 11
    assert report.removed_by_reason == {}
