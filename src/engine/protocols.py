"""
Protocol interfaces and result dataclasses for the Index Engine and
sibling modules.

These define the contract that the real implementations must satisfy.
The API layer depends only on these types — never on concrete engine
internals. Because we use ``typing.Protocol``, the real engine classes
just need matching method signatures (structural subtyping); they do
NOT need to inherit from these protocols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


# ── Result dataclasses ─────────────────────────────────────────────


@dataclass
class RouteIndex:
    """Index result for a single route."""

    route: str
    index: float
    mom: Optional[float]  # month-over-month change (%)
    weight: float
    contribution: float
    data_source: str  # "real" | "synthetic"


@dataclass
class IndexResult:
    """Complete result of an index calculation."""

    national_index: float
    mom: Optional[float]  # month-over-month change (%)
    yoy: Optional[float]  # year-over-year change (%)
    base_period: str
    current_period: str
    route_indices: list[RouteIndex]
    quality_score: Optional[float]
    data_source: str  # "real" | "synthetic"
    flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeseriesPoint:
    """A single point in the index time series."""

    period: str
    index: float
    mom: Optional[float]
    yoy: Optional[float]
    data_source: str  # "real" | "synthetic"


@dataclass
class RouteHealth:
    """Health assessment for a single route."""

    route: str
    observations: int
    valid: int
    rejected: int
    flagged: int
    health_score: float
    status: str  # "healthy" | "degraded" | "critical"


@dataclass
class SourceHealth:
    """Health assessment for a data source."""

    source: str
    observations: int
    valid: int
    rejected: int
    reliability_score: float


@dataclass
class QualityReport:
    """Complete data quality assessment."""

    total_observations: int
    valid: int
    rejected: int
    flagged: int
    rejection_reasons: dict[str, int]
    quality_score: float
    quality_grade: str  # "A" | "B" | "C" | "D" | "F"
    route_health: list[RouteHealth]
    source_health: list[SourceHealth]
    data_source: str  # "real" | "synthetic"


@dataclass
class RouteAnalysis:
    """Analysis result for a single route."""

    route: str
    route_index: float
    mom: Optional[float]
    weight: float
    contribution: float
    traffic_coverage: float
    status: str  # "active" | "inactive" | "new"
    data_source: str  # "real" | "synthetic"


@dataclass
class NewsEvent:
    """A single news or event item relevant to a route."""

    headline: str
    source: str
    publication_date: str
    url: Optional[str]
    relevance_score: float
    data_source: str  # "real" | "synthetic"


@dataclass
class RouteContext:
    """News/event context for a route."""

    route: str
    significant_movement: bool
    movement_direction: Optional[str]  # "up" | "down" | None
    movement_pct: Optional[float]
    events: list[NewsEvent]
    data_source: str  # "real" | "synthetic"


# ── Protocol interfaces ───────────────────────────────────────────


@runtime_checkable
class IndexEngineProtocol(Protocol):
    """Interface for the Airfare Price Index engine."""

    def calculate_index(
        self,
        observations: list[dict[str, Any]],
        base_period: str,
        current_period: str,
        config: Optional[dict[str, Any]] = None,
    ) -> IndexResult:
        """
        Calculate the composite airfare price index.

        Parameters
        ----------
        observations : list[dict]
            Each dict must contain at minimum:
            ``{"route": str, "fare": float, "date": str, "source": str}``
        base_period : str
            Base period in ``YYYY-MM`` format.
        current_period : str
            Current period in ``YYYY-MM`` format.
        config : dict, optional
            Engine-specific configuration overrides.

        Returns
        -------
        IndexResult
        """
        ...

    def get_timeseries(
        self,
        start_date: str,
        end_date: str,
    ) -> list[TimeseriesPoint]:
        """
        Return index values for a date range.

        Parameters
        ----------
        start_date : str
            Start of range in ``YYYY-MM`` format.
        end_date : str
            End of range in ``YYYY-MM`` format.

        Returns
        -------
        list[TimeseriesPoint]
        """
        ...


@runtime_checkable
class DataQualityProtocol(Protocol):
    """Interface for the Data Quality assessment module."""

    def assess_quality(
        self,
        observations: list[dict[str, Any]],
    ) -> QualityReport:
        """
        Assess the quality of a batch of fare observations.

        Parameters
        ----------
        observations : list[dict]
            Raw fare observations.

        Returns
        -------
        QualityReport
        """
        ...


@runtime_checkable
class RouteAnalyticsProtocol(Protocol):
    """Interface for the Route Analytics module."""

    def get_route_analysis(self) -> list[RouteAnalysis]:
        """
        Return analysis for all tracked routes.

        Returns
        -------
        list[RouteAnalysis]
        """
        ...


@runtime_checkable
class NewsContextProtocol(Protocol):
    """Interface for the News / Event Context module."""

    async def get_route_context(self, route_code: str) -> RouteContext:
        """
        Fetch contextual news/events for a given route.

        Parameters
        ----------
        route_code : str
            IATA route code, e.g. ``"DEL-BOM"``.

        Returns
        -------
        RouteContext

        Raises
        ------
        ValueError
            If the route code is unknown or invalid.
        """
        ...
