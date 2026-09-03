"""Scraper output -> ForecastingDataset adapter.

STAGE: Scraper -> Forecasting integration layer. This module is a THIN
adapter: it reads scraper-produced JSONL files (the on-disk shape
documented in the scraper package's ``storage.py`` -- one JSON object per
line, matching ``RawFareObservation.to_record()`` / docs/data_contract.md)
and hands the resulting records straight to
``data_access.build_forecasting_dataset()``. It deliberately does NOT:

  - recompute, duplicate, or reimplement any index/aggregation/cleaning/
    weighting logic (index_engine remains the sole authority for that,
    same as data_access.py's own scope statement);
  - reimplement data_quality's business-rule validation (suspicious-fare
    thresholds, duplicate detection, staleness, source/route health --
    see that package's ``pipeline.validate_fare_batch``). If scraper
    output has already been through that pipeline (i.e. loaded from a
    ``data/validated/fares/`` tree, which is already VALID+FLAGGED only,
    never REJECTED -- see ``scraper.storage``'s module docstring), this
    module's own filtering below is a no-op safety net. If pointed at
    ``data/raw/fares/`` instead, unvalidated rows are passed straight
    through structurally intact records -- this module only drops rows
    that are structurally unusable (missing a required field, or a
    non-positive/non-numeric fare), never anything data_quality's
    business rules would flag or reject;
  - fill, interpolate, forward-fill, or otherwise guess any missing
    value;
  - silently treat synthetic (``is_mock=True``) observations as real
    historical data -- every result this module returns reports how much
    of the loaded input was real vs. synthetic, and refuses to silently
    mix the two (see ``allow_mock``).

The forecasting/index_engine layers this module builds on were already
validated end-to-end (including against real SerpApi-sourced
observations) before this adapter was written; this module's only job is
removing the manual step of turning scraper JSONL files into the
observations argument ``build_forecasting_dataset()`` already accepts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import pandas as pd

from .data_access import ForecastingDataset, build_forecasting_dataset

#: The 8 required fields per docs/data_contract.md / RawFareObservation --
#: mirrors data_access.py's own reliance on index_engine.config.REQUIRED_COLUMNS
#: without importing a package (scraper) this module does not otherwise need.
REQUIRED_FIELDS: Tuple[str, ...] = (
    "observation_id",
    "airline",
    "origin",
    "destination",
    "flight_date",
    "booking_date",
    "total_fare",
    "currency",
)

PathLike = Union[str, Path]


@dataclass
class ScraperIngestResult:
    """Everything a caller needs to know about how a ``ForecastingDataset``
    was assembled from scraper output -- provenance that ``ForecastingDataset``
    itself does not carry, so it is never confused with a dataset built any
    other way.

    ``is_synthetic_data``: True only if EVERY loaded, usable record has
    ``is_mock=True``. Pass this straight through to
    ``forecast_national_index(..., is_synthetic_data=...)`` /
    ``evaluate_national_baselines(..., is_synthetic_data=...)`` --
    never hard-code ``False`` for a dataset built this way.

    ``is_mixed_data``: True if the loaded input contains BOTH real and
    synthetic observations. This is never resolved automatically -- a
    caller must either filter one out before calling, or pass
    ``allow_mock=True`` to acknowledge the mix explicitly.
    """

    dataset: ForecastingDataset
    total_records_loaded: int
    real_record_count: int
    synthetic_record_count: int
    is_synthetic_data: bool
    is_mixed_data: bool
    skipped_malformed_count: int
    source_paths: List[str]
    warnings: List[str] = field(default_factory=list)


def _read_jsonl(path: PathLike) -> List[dict]:
    records: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_scraper_jsonl(paths: Union[PathLike, Sequence[PathLike]]) -> List[dict]:
    """Load one or more scraper-output JSONL files.

    Matches the on-disk shape ``scraper.storage.write_raw_run`` /
    ``write_validated_run`` produce: one JSON object per line, each shaped
    like ``RawFareObservation.to_record()``. Purely a file-format reader --
    performs no filtering, validation, or deduplication of any kind.
    """
    path_list: List[PathLike] = [paths] if isinstance(paths, (str, Path)) else list(paths)
    records: List[dict] = []
    for p in path_list:
        records.extend(_read_jsonl(p))
    return records


def _filter_structurally_usable(records: Sequence[dict]) -> Tuple[List[dict], int]:
    """Drop records missing any of the 8 data-contract-required fields, or
    with a non-positive / non-numeric ``total_fare``.

    This is schema-presence checking only -- a record dropped here is one
    ``build_forecasting_dataset()`` / ``index_engine`` structurally could
    not have used anyway (the same 8 fields index_engine's own required
    columns check demands). It is NOT a reimplementation of any
    data_quality business rule (suspicious-fare bounds, duplicate
    detection, staleness, etc. all remain out of scope here).
    """
    kept: List[dict] = []
    dropped = 0
    for record in records:
        if not all(record.get(f) not in (None, "") for f in REQUIRED_FIELDS):
            dropped += 1
            continue
        try:
            if float(record["total_fare"]) <= 0:
                dropped += 1
                continue
        except (TypeError, ValueError):
            dropped += 1
            continue
        kept.append(record)
    return kept, dropped


def build_dataset_from_scraper_output(
    paths: Union[PathLike, Sequence[PathLike]],
    base_period: str,
    periods: Optional[List[str]] = None,
    weights: Optional[pd.DataFrame] = None,
    config=None,
    volatility_config=None,
    traffic_weight_coverage: Optional[float] = None,
    allow_mock: bool = False,
) -> ScraperIngestResult:
    """Build a ``ForecastingDataset`` directly from scraper JSONL output.

    Reuses ``build_forecasting_dataset()`` unchanged for every index/period
    computation -- this function's only job is: locate+parse scraper JSONL
    file(s), drop structurally-unusable rows (see
    ``_filter_structurally_usable``), and clearly report how much of the
    input was synthetic (``is_mock=True``) vs. real before handing the rest
    on.

    Parameters
    ----------
    paths:
        One path, or a sequence of paths, to scraper JSONL file(s) --
        typically a single ``data/validated/fares/<run_id>.jsonl`` (the
        already-quality-filtered, recommended input), or one or more
        ``data/raw/fares/<run_id>.jsonl`` files if data_quality has not run.
    base_period, periods, weights, config, volatility_config,
    traffic_weight_coverage:
        Passed straight through to ``build_forecasting_dataset()`` -- see
        that function's docstring; this adapter sets no defaults or
        reinterpretation of any of these.
    allow_mock:
        Default ``False``: if the loaded, usable records mix real and
        synthetic (``is_mock=True``) observations, this function raises
        ``ValueError`` rather than silently building a dataset that blends
        the two. Pass ``True`` only when mixing real and synthetic data is
        a deliberate, understood choice (e.g. a demo/test scenario) --
        never to make an error disappear. A batch that is ALL synthetic,
        or ALL real, never raises regardless of this flag; it is only ever
        checked for a *mix* of both.

    Raises
    ------
    ValueError
        If the input mixes real and synthetic observations without
        ``allow_mock=True``, or if zero structurally-usable records remain
        after filtering.
    index_engine.exceptions.InsufficientDataError
        Propagated from ``build_forecasting_dataset()``, not caught -- see
        that function's docstring.
    """
    raw_records = load_scraper_jsonl(paths)
    total_loaded = len(raw_records)

    usable, skipped_malformed = _filter_structurally_usable(raw_records)

    real_count = sum(1 for r in usable if not r.get("is_mock", False))
    synthetic_count = sum(1 for r in usable if r.get("is_mock", False))
    is_synthetic_data = synthetic_count > 0 and real_count == 0
    is_mixed_data = synthetic_count > 0 and real_count > 0

    if is_mixed_data and not allow_mock:
        raise ValueError(
            f"Input mixes {real_count} real and {synthetic_count} synthetic "
            "(is_mock=True) observation(s). This adapter refuses to silently "
            "blend real and synthetic data into one dataset. Pass "
            "allow_mock=True only if mixing them is a deliberate, understood "
            "choice; otherwise filter the input to one or the other first."
        )

    if not usable:
        raise ValueError(
            f"No structurally-usable observations after filtering: "
            f"{total_loaded} loaded, {skipped_malformed} dropped for a "
            "missing required field or invalid total_fare."
        )

    warnings: List[str] = []
    if skipped_malformed:
        warnings.append(
            f"Dropped {skipped_malformed} record(s) missing a required field "
            "or with an invalid total_fare during ingest."
        )
    if is_mixed_data:
        warnings.append(
            f"Input mixes real ({real_count}) and synthetic "
            f"(is_mock=True, {synthetic_count}) observations (allow_mock=True)."
        )
    if is_synthetic_data:
        warnings.append(
            "ALL loaded observations are synthetic (is_mock=True) -- this "
            "dataset is NOT real historical data."
        )

    dataset = build_forecasting_dataset(
        observations=usable,
        base_period=base_period,
        periods=periods,
        weights=weights,
        config=config,
        volatility_config=volatility_config,
        traffic_weight_coverage=traffic_weight_coverage,
    )
    dataset.warnings = list(dataset.warnings) + warnings

    path_list: List[PathLike] = [paths] if isinstance(paths, (str, Path)) else list(paths)

    return ScraperIngestResult(
        dataset=dataset,
        total_records_loaded=total_loaded,
        real_record_count=real_count,
        synthetic_record_count=synthetic_count,
        is_synthetic_data=is_synthetic_data,
        is_mixed_data=is_mixed_data,
        skipped_malformed_count=skipped_malformed,
        source_paths=[str(p) for p in path_list],
        warnings=warnings,
    )
