"""Booking-horizon (advance-purchase window) analytics.

STAGE: Booking-Horizon Analytics. The project's strategy doc frames fare
behavior across T+1 through T+45 advance-purchase windows (how far ahead
of the flight a fare was observed) as a distinct signal from the
single-snapshot national/route index Stage 1/2 already forecast -- a fare
observed 2 days before departure and one observed 40 days before departure
for the *same* flight_date are not interchangeable data points; blending
them into one period average hides exactly the "how does price move as
departure approaches" behavior this stage exists to expose.

CONTRACT INSPECTION (done before writing this module, not assumed):
``RawFareObservation`` (scraper.models) has no ``advance_purchase_days``
field. It has ``flight_date`` and ``booking_date`` as two of its 8
*required* (non-Optional) fields -- confirmed by reading the dataclass
directly. Every scraper source that ever actually returns an observation
(``mock_source.py``, ``serpapi_source.py``, ``yatra_source.py``) sets both
fields when constructing ``RawFareObservation``; ``indigo_source.py`` never
returns real data at all (always ``SOURCE_UNAVAILABLE`` -- no live call is
implemented), so it cannot violate this. A 90-record real+mock sample
(``data/raw/fares/*.jsonl``) had zero missing values for either field.
``advance_purchase_days`` is therefore cleanly derivable as
``(flight_date - booking_date).days`` forecasting-side, on the *raw*
observation, with no scraper-side change needed and nothing invented.

This module never touches ``ForecastingDataset``/``data_access.py``
directly for this purpose: by the time raw observations are aggregated
into a ``ForecastingDataset`` (one row per period/route), the per-
observation ``booking_date`` is gone -- collapsed into the period/route
index the same way ``fare_class``, ``stops``, etc. already are. So booking-
horizon partitioning has to happen on raw observations, *before*
aggregation, one call to ``build_forecasting_dataset()`` per window --
reusing the exact same aggregation path Stage 1/2 use, not reimplementing
any index math per window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

from .data_access import ForecastingDataset, build_forecasting_dataset
from .ingest import (
    PathLike,
    _filter_structurally_usable,
    load_scraper_jsonl,
)
from .results import STATUS_INSUFFICIENT_DATA, STATUS_OK

try:
    from index_engine.exceptions import InsufficientDataError
except ImportError:  # pragma: no cover - exercised only if index_engine's
    # package layout changes; treated as "no such class" rather than a
    # hard import failure so this module still loads.
    class InsufficientDataError(Exception):
        pass


@dataclass(frozen=True)
class BookingWindow:
    """One advance-purchase bucket, inclusive on both ends (days)."""

    name: str
    min_days: int
    max_days: int

    def contains(self, days: int) -> bool:
        return self.min_days <= days <= self.max_days


#: T+1 through T+45, in five roughly-equal buckets. Five was chosen over
#: single-day granularity because at this project's current real-data
#: volume (a handful of scrape runs), single-day bins would mostly be
#: empty or single-observation -- not a meaningful window average. Five
#: buckets keeps each one wide enough to hold multiple observations per
#: scrape run while still separating "last week," "two weeks out," "three
#: weeks out," "about a month out," and "5-6 weeks out" -- the coarse
#: shape the strategy doc's booking-horizon framing cares about. Boundaries
#: are explicit and simple (7-day steps, final bucket wider to reach 45)
#: rather than derived from any statistical binning -- consistent with
#: this codebase's stated preference for explicit logic over cleverness.
BOOKING_WINDOWS: Tuple[BookingWindow, ...] = (
    BookingWindow("T1_7", 1, 7),
    BookingWindow("T8_14", 8, 14),
    BookingWindow("T15_21", 15, 21),
    BookingWindow("T22_30", 22, 30),
    BookingWindow("T31_45", 31, 45),
)

NO_DATA = "NO_DATA"


def compute_advance_purchase_days(record: dict) -> Optional[int]:
    """``(flight_date - booking_date).days`` for one scraper record.

    Returns ``None`` if either date is missing or not a parseable
    ``YYYY-MM-DD`` string -- never a guessed/defaulted value.
    """
    flight_date_raw = record.get("flight_date")
    booking_date_raw = record.get("booking_date")
    if not flight_date_raw or not booking_date_raw:
        return None
    try:
        flight_date = date.fromisoformat(str(flight_date_raw))
        booking_date = date.fromisoformat(str(booking_date_raw))
    except ValueError:
        return None
    return (flight_date - booking_date).days


def classify_booking_window(
    advance_purchase_days: Optional[int],
    windows: Sequence[BookingWindow] = BOOKING_WINDOWS,
) -> Optional[str]:
    """Window name for ``advance_purchase_days``, or ``None`` if it's
    ``None``, negative (booking after flight -- a data error, not a valid
    horizon), or outside every window's [min_days, max_days] range (e.g.
    0 = same-day, or > the last window's max)."""
    if advance_purchase_days is None:
        return None
    for window in windows:
        if window.contains(advance_purchase_days):
            return window.name
    return None


@dataclass
class BookingHorizonPartition:
    """Result of splitting raw records by booking window, with an honest
    accounting of every record that did NOT end up in a window."""

    window_records: Dict[str, List[dict]]
    total_records: int
    missing_date_count: int
    invalid_date_count: int
    out_of_range_count: int
    negative_horizon_count: int


def partition_by_booking_window(
    records: Sequence[dict],
    windows: Sequence[BookingWindow] = BOOKING_WINDOWS,
) -> BookingHorizonPartition:
    """Split structurally-usable records into booking windows.

    Every input record is accounted for exactly once: either it lands in
    a window, or it is counted in one of ``missing_date_count`` (no
    flight_date/booking_date), ``invalid_date_count`` (unparseable date
    string), ``negative_horizon_count`` (booking_date after flight_date --
    a data error), or ``out_of_range_count`` (a valid, non-negative
    horizon outside T+1..T+45, e.g. same-day or > 45 days out). Nothing is
    dropped silently or filled in.
    """
    window_records: Dict[str, List[dict]] = {w.name: [] for w in windows}
    missing = invalid = out_of_range = negative = 0

    for record in records:
        flight_date_raw = record.get("flight_date")
        booking_date_raw = record.get("booking_date")
        if not flight_date_raw or not booking_date_raw:
            missing += 1
            continue
        try:
            days = compute_advance_purchase_days(record)
        except Exception:  # defensive; compute_advance_purchase_days
            days = None
        if days is None:
            invalid += 1
            continue
        if days < 0:
            negative += 1
            continue
        window_name = classify_booking_window(days, windows)
        if window_name is None:
            out_of_range += 1
            continue
        window_records[window_name].append(record)

    return BookingHorizonPartition(
        window_records=window_records,
        total_records=len(records),
        missing_date_count=missing,
        invalid_date_count=invalid,
        out_of_range_count=out_of_range,
        negative_horizon_count=negative,
    )


@dataclass
class BookingWindowDataset:
    """One booking window's forecasting-ready dataset, or an explicit
    reason there isn't one."""

    window: str
    record_count: int
    status: str  # STATUS_OK / STATUS_INSUFFICIENT_DATA / NO_DATA
    dataset: Optional[ForecastingDataset] = None
    error: Optional[str] = None


@dataclass
class BookingHorizonAnalysis:
    """All booking windows for one set of scraper input, plus the
    partition accounting and cross-window provenance."""

    windows: Dict[str, BookingWindowDataset]
    partition: BookingHorizonPartition
    total_records_loaded: int
    skipped_malformed_count: int
    real_record_count: int
    synthetic_record_count: int
    is_synthetic_data: bool
    is_mixed_data: bool
    source_paths: List[str]
    warnings: List[str] = field(default_factory=list)


def _build_window_dataset(
    window_name: str,
    window_records: List[dict],
    base_period: str,
    periods: Optional[List[str]],
    weights: Optional[pd.DataFrame],
    config,
    volatility_config,
    traffic_weight_coverage: Optional[float],
) -> BookingWindowDataset:
    if not window_records:
        return BookingWindowDataset(window=window_name, record_count=0, status=NO_DATA)
    try:
        dataset = build_forecasting_dataset(
            observations=window_records,
            base_period=base_period,
            periods=periods,
            weights=weights,
            config=config,
            volatility_config=volatility_config,
            traffic_weight_coverage=traffic_weight_coverage,
        )
    except (InsufficientDataError, ValueError) as exc:
        return BookingWindowDataset(
            window=window_name,
            record_count=len(window_records),
            status=STATUS_INSUFFICIENT_DATA,
            error=str(exc),
        )
    return BookingWindowDataset(
        window=window_name,
        record_count=len(window_records),
        status=STATUS_OK,
        dataset=dataset,
    )


def build_booking_horizon_datasets(
    paths: Union[PathLike, Sequence[PathLike]],
    base_period: str,
    periods: Optional[List[str]] = None,
    weights: Optional[pd.DataFrame] = None,
    config=None,
    volatility_config=None,
    traffic_weight_coverage: Optional[float] = None,
    allow_mock: bool = False,
    windows: Sequence[BookingWindow] = BOOKING_WINDOWS,
) -> BookingHorizonAnalysis:
    """Load scraper JSONL output, partition by booking window, and build
    one ``ForecastingDataset`` per window that has usable records.

    Reuses ``ingest.py``'s file-loading and structural filtering, and
    ``build_forecasting_dataset()`` for every window's index/period
    computation -- no aggregation logic is duplicated here. A window with
    zero usable records after partitioning gets an explicit ``NO_DATA``
    entry (no ``ForecastingDataset``, nothing invented); a window whose
    records exist but that ``build_forecasting_dataset()`` itself cannot
    build a dataset from gets ``STATUS_INSUFFICIENT_DATA`` with the
    underlying error preserved -- one window's failure never prevents the
    others from building.

    ``allow_mock`` has the same meaning as ``ingest.build_dataset_from_scraper_output``:
    real and synthetic (``is_mock=True``) records loaded together raise
    ``ValueError`` unless explicitly acknowledged.
    """
    path_list: List[PathLike] = [paths] if isinstance(paths, (str, Path)) else list(paths)
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

    partition = partition_by_booking_window(usable, windows)

    window_datasets: Dict[str, BookingWindowDataset] = {}
    for window in windows:
        window_datasets[window.name] = _build_window_dataset(
            window.name,
            partition.window_records[window.name],
            base_period,
            periods,
            weights,
            config,
            volatility_config,
            traffic_weight_coverage,
        )

    warnings: List[str] = []
    if skipped_malformed:
        warnings.append(
            f"Dropped {skipped_malformed} record(s) missing a required field "
            "or with an invalid total_fare during ingest."
        )
    if partition.missing_date_count:
        warnings.append(
            f"{partition.missing_date_count} record(s) missing flight_date "
            "or booking_date -- excluded from every window."
        )
    if partition.invalid_date_count:
        warnings.append(
            f"{partition.invalid_date_count} record(s) had an unparseable "
            "flight_date/booking_date -- excluded from every window."
        )
    if partition.negative_horizon_count:
        warnings.append(
            f"{partition.negative_horizon_count} record(s) had booking_date "
            "after flight_date (negative advance-purchase) -- excluded, "
            "not treated as T+0."
        )
    if partition.out_of_range_count:
        warnings.append(
            f"{partition.out_of_range_count} record(s) had a valid "
            f"advance-purchase horizon outside T+{windows[0].min_days}..T+{windows[-1].max_days} "
            "-- excluded from every window."
        )
    if is_mixed_data:
        warnings.append(
            f"Input mixes real ({real_count}) and synthetic "
            f"(is_mock=True, {synthetic_count}) observations (allow_mock=True)."
        )
    if is_synthetic_data:
        warnings.append(
            "ALL loaded observations are synthetic (is_mock=True) -- these "
            "booking-window datasets are NOT real historical data."
        )

    return BookingHorizonAnalysis(
        windows=window_datasets,
        partition=partition,
        total_records_loaded=total_loaded,
        skipped_malformed_count=skipped_malformed,
        real_record_count=real_count,
        synthetic_record_count=synthetic_count,
        is_synthetic_data=is_synthetic_data,
        is_mixed_data=is_mixed_data,
        source_paths=[str(p) for p in path_list],
        warnings=warnings,
    )
