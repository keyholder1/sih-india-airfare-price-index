"""Duplicate removal and outlier detection.

Runs after :mod:`index_engine.validation` (structural checks) and after
:mod:`index_engine.normalization` has attached ``route``, ``period`` and
``standardized_fare``. Every dropped row is tagged with a reason rather than
silently discarded.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from .config import IndexConfig
from .models import CleaningReport

REASON_DUPLICATE = "DUPLICATE"
REASON_OUTLIER_IQR = "OUTLIER_IQR"
REASON_OUTLIER_MAD = "OUTLIER_MAD"
REASON_OUTLIER_PERCENTILE = "OUTLIER_PERCENTILE"


def _drop_duplicates(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    is_dup = df.duplicated(subset=["observation_id"], keep="first")
    return df[~is_dup].copy(), df[is_dup].copy()


def _flag_outliers_iqr(fares: pd.Series, multiplier: float) -> pd.Series:
    q1, q3 = fares.quantile(0.25), fares.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=fares.index)
    lower, upper = q1 - multiplier * iqr, q3 + multiplier * iqr
    return (fares < lower) | (fares > upper)


def _flag_outliers_mad(fares: pd.Series, threshold: float) -> pd.Series:
    median = fares.median()
    mad = (fares - median).abs().median()
    if mad == 0:
        return pd.Series(False, index=fares.index)
    modified_z = 0.6745 * (fares - median) / mad
    return modified_z.abs() > threshold


def _flag_outliers_percentile(fares: pd.Series, bounds: Tuple[float, float]) -> pd.Series:
    lower, upper = fares.quantile(bounds[0]), fares.quantile(bounds[1])
    return (fares < lower) | (fares > upper)


def _flag_outliers(df: pd.DataFrame, config: IndexConfig) -> pd.Series:
    """Flag outliers per (route, period) group, since a fare that is normal
    on a long-haul trunk route may be extreme on a short regional hop."""
    flags = pd.Series(False, index=df.index)
    if config.outlier_method == "none":
        return flags

    for _, group in df.groupby(["route", "period"]):
        fares = group["standardized_fare"]
        if len(fares) < 4:
            # Not enough points in this group for a meaningful outlier test.
            continue
        if config.outlier_method == "iqr":
            group_flags = _flag_outliers_iqr(fares, config.outlier_iqr_multiplier)
        elif config.outlier_method == "mad":
            group_flags = _flag_outliers_mad(fares, config.outlier_mad_threshold)
        elif config.outlier_method == "percentile":
            group_flags = _flag_outliers_percentile(fares, config.outlier_percentile_bounds)
        else:
            raise ValueError(f"Unknown outlier_method: {config.outlier_method}")
        flags.loc[group_flags.index] = group_flags
    return flags


def clean_observations(df: pd.DataFrame, config: IndexConfig, total_input: int) -> Tuple[pd.DataFrame, CleaningReport]:
    """Remove duplicates and outliers, returning survivors plus a report.

    ``total_input`` is the count of rows entering *this* function — i.e.
    after validation, before cleaning (``index.py`` calls this with
    ``len(valid)``). The ``CleaningReport`` returned here only accounts
    for what happens inside this function; ``index.py``'s
    ``_merge_cleaning_report`` re-derives the true original-dataset
    ``total_input``/``total_removed`` by additionally folding in whatever
    validation() rejected upstream, which this function never sees.
    """
    removed_by_reason: dict = {}

    deduped, dupes = _drop_duplicates(df)
    if len(dupes):
        removed_by_reason[REASON_DUPLICATE] = len(dupes)

    outlier_flags = _flag_outliers(deduped, config)
    reason_label = {
        "iqr": REASON_OUTLIER_IQR,
        "mad": REASON_OUTLIER_MAD,
        "percentile": REASON_OUTLIER_PERCENTILE,
    }.get(config.outlier_method)
    if reason_label and outlier_flags.any():
        removed_by_reason[reason_label] = int(outlier_flags.sum())

    clean = deduped[~outlier_flags].copy()

    total_removed = total_input - len(clean)
    # Any removal that happened upstream in validation() isn't visible here,
    # so the caller (index.py) merges that count in separately.
    report = CleaningReport(
        total_input=total_input,
        total_valid=len(clean),
        total_removed=total_removed,
        removed_by_reason=removed_by_reason,
    )
    return clean, report
