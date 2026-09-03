"""Engine configuration.

All statistical choices that could reasonably be made a different way are
exposed here rather than hard-coded, so the methodology can be tuned or
swapped later without touching the calculation code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

RepresentativeMethod = Literal["median", "mean", "trimmed_mean"]
OutlierMethod = Literal["iqr", "mad", "percentile", "none"]
AggregationMethod = Literal["arithmetic", "geometric"]

#: Booking-horizon buckets, in days between booking_date and flight_date.
#: (lower_inclusive, upper_inclusive_or_None) pairs, labelled left-to-right.
BOOKING_HORIZON_BUCKETS: Tuple[Tuple[str, int, Optional[int]], ...] = (
    ("0-3", 0, 3),
    ("4-7", 4, 7),
    ("8-14", 8, 14),
    ("15-30", 15, 30),
    ("31-60", 31, 60),
    ("61+", 61, None),
)


@dataclass
class IndexConfig:
    """Configuration for a single :class:`AirfarePriceIndex` instance.

    Parameters
    ----------
    base_period:
        Reference period whose representative fares are pinned to an index
        value of 100, e.g. ``"2026-01"``.
    representative_method:
        How the "typical" fare for a route/period is summarised from many
        observations. Defaults to the median because airfares are strongly
        right-skewed (a handful of last-minute or premium fares can be many
        multiples of the typical fare) and the median is not pulled by those
        extremes the way a mean is.
    trimmed_mean_proportion:
        Fraction trimmed from each tail when ``representative_method`` is
        ``"trimmed_mean"``.
    outlier_method:
        Statistical rule used to flag (not silently drop) extreme fares
        within a route/period before the representative fare is computed.
    fare_field:
        Which column of a standardized observation is treated as "the"
        comparable fare. Default is ``total_fare`` (mandatory fare + taxes
        + fees, excluding optional add-ons) per the standardized fare
        definition documented in docs/methodology.md.
    booking_horizon_filter:
        If set to one of the bucket labels in ``BOOKING_HORIZON_BUCKETS``
        (e.g. ``"15-30"``), only observations booked in that horizon are
        used. If ``None``, all booking horizons are pooled together.
    min_observations_per_route_period:
        Minimum number of surviving observations required before a route's
        representative fare for a period is considered reliable. Below this,
        the route/period is flagged ``INSUFFICIENT_DATA`` instead of
        producing a number.
    aggregation_method:
        How route-level indices are combined into the national index.
        ``"arithmetic"`` (weighted arithmetic mean of route indices) is the
        default and is consistent with how headline CPI aggregates
        elementary indices using fixed base-period expenditure weights
        (Laspeyres-style). ``"geometric"`` (weighted geometric mean of price
        relatives) is offered as an alternative — it is less sensitive to
        any single route index spiking, at the cost of being less
        intuitive to explain and slightly understating pure income-effect
        inflation. See docs/methodology.md for the full discussion.
    """

    base_period: str
    representative_method: RepresentativeMethod = "median"
    trimmed_mean_proportion: float = 0.1
    outlier_method: OutlierMethod = "iqr"
    outlier_iqr_multiplier: float = 1.5
    outlier_mad_threshold: float = 3.5
    outlier_percentile_bounds: Tuple[float, float] = (0.01, 0.99)
    fare_field: str = "total_fare"
    booking_horizon_filter: Optional[str] = None
    min_observations_per_route_period: int = 3
    aggregation_method: AggregationMethod = "arithmetic"

    def __post_init__(self) -> None:
        valid_buckets = {b[0] for b in BOOKING_HORIZON_BUCKETS}
        if self.booking_horizon_filter is not None and self.booking_horizon_filter not in valid_buckets:
            raise ValueError(
                f"booking_horizon_filter must be one of {sorted(valid_buckets)} or None, "
                f"got {self.booking_horizon_filter!r}"
            )
        if not 0 <= self.trimmed_mean_proportion < 0.5:
            raise ValueError("trimmed_mean_proportion must be in [0, 0.5)")
        if self.min_observations_per_route_period < 1:
            raise ValueError("min_observations_per_route_period must be >= 1")


REQUIRED_COLUMNS: Tuple[str, ...] = (
    "observation_id",
    "airline",
    "origin",
    "destination",
    "flight_date",
    "booking_date",
    "total_fare",
    "currency",
)
