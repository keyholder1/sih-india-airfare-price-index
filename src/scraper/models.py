"""Typed data structures for the scraper layer.

Same convention as ``index_engine.models`` / ``data_quality.models``: plain
dataclasses with ``to_dict()``. ``RawFareObservation.to_record()`` is the
one place that must stay in sync with ``docs/data_contract.md`` — every
other module downstream (``data_quality``, ``index_engine``) is the
authority on what happens to a record after that point, not this one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Dict, List, Literal, Optional

#: What happened when a source was asked for one route/date combination.
#: ``SUCCESS`` can still carry zero observations (see EMPTY_RESULT vs
#: SUCCESS-with-zero — kept distinct: EMPTY_RESULT means the source
#: responded normally but had nothing to offer; SUCCESS always has >=1).
CollectionStatus = Literal[
    "SUCCESS",
    "EMPTY_RESULT",
    "TIMEOUT",
    "HTTP_ERROR",
    "RATE_LIMITED",
    "PARSE_ERROR",
    "MALFORMED_RESPONSE",
    "SOURCE_UNAVAILABLE",
]

TERMINAL_FAILURE_STATUSES: tuple = (
    "EMPTY_RESULT",
    "TIMEOUT",
    "HTTP_ERROR",
    "RATE_LIMITED",
    "PARSE_ERROR",
    "MALFORMED_RESPONSE",
    "SOURCE_UNAVAILABLE",
)


@dataclass
class RawFareObservation:
    """One collected fare, before Data Quality has looked at it.

    Field set mirrors ``docs/data_contract.md`` exactly: the first eight
    are required there, the next eleven are the documented optional set.
    Provenance fields (``source_url``, ``scraped_at``, ``run_id``,
    ``is_mock``) are additional columns the Data Quality/Index Engine
    schema checks tolerate but don't require — see
    ``index_engine.validation.validate_observations`` and
    ``data_quality.validation.check_schema``, both of which only check
    that the *required* columns are present and never reject on extras.
    """

    # --- required (docs/data_contract.md "Required fields") ---
    observation_id: str
    airline: str
    origin: str
    destination: str
    flight_date: str  # YYYY-MM-DD
    booking_date: str  # YYYY-MM-DD
    total_fare: float
    currency: str

    # --- optional (docs/data_contract.md "Optional fields") ---
    timestamp: Optional[str] = None
    source: Optional[str] = None
    fare_class: Optional[str] = None
    fare_type: Optional[str] = None
    base_fare: Optional[float] = None
    taxes: Optional[float] = None
    fees: Optional[float] = None
    stops: Optional[int] = None
    duration: Optional[float] = None
    baggage: Optional[str] = None
    availability: Optional[bool] = None

    # --- provenance (not part of the data contract; extra columns) ---
    source_url: Optional[str] = None
    scraped_at: Optional[str] = None
    run_id: Optional[str] = None
    is_mock: bool = False

    def to_record(self) -> dict:
        """The flat dict shape handed to ``data_quality.validate_fare_batch``
        / ``AirfarePriceIndex.calculate`` — a plain dict, matching what
        every other producer in this repo (e.g.
        ``examples/generate_sample_fares.py``) already hands the engine."""
        return asdict(self)


@dataclass
class SourceCallResult:
    """Outcome of one ``FareSource.search_fares(...)`` call."""

    status: CollectionStatus
    observations: List[RawFareObservation] = field(default_factory=list)
    error_detail: Optional[str] = None
    attempts: int = 1

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "observation_count": len(self.observations),
            "error_detail": self.error_detail,
            "attempts": self.attempts,
        }


@dataclass
class SourceRunSummary:
    """Aggregated outcome for one source across an entire run."""

    source: str
    routes_requested: int
    routes_successful: int
    routes_failed: int
    routes_attempted: List[str]
    observations_collected: int
    failure_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_route_attempts_row(self) -> dict:
        """Shaped exactly as ``data_quality.health`` documents its
        ``route_attempts`` input — feed a list of these straight into
        ``validate_fare_batch(raw_data, route_attempts=[...])``."""
        return {
            "source": self.source,
            "routes_requested": self.routes_requested,
            "routes_successful": self.routes_successful,
            "routes_failed": self.routes_failed,
            "routes_attempted": self.routes_attempted,
        }


@dataclass
class ScrapeRunReport:
    """Full structured report for one scrape run — see docs/scraper.md
    §Scraper health for the human-readable rendering."""

    run_id: str
    mode: Literal["mock", "live"]
    started_at: str
    finished_at: str
    routes_requested: int
    routes_successful: int
    routes_failed: int
    observations_collected: int
    source_summaries: List[SourceRunSummary] = field(default_factory=list)
    failure_reasons: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "routes_requested": self.routes_requested,
            "routes_successful": self.routes_successful,
            "routes_failed": self.routes_failed,
            "observations_collected": self.observations_collected,
            "source_summaries": [s.to_dict() for s in self.source_summaries],
            "failure_reasons": self.failure_reasons,
        }

    def to_route_attempts(self) -> List[dict]:
        """Ready to pass as ``data_quality.validate_fare_batch(...,
        route_attempts=report.to_route_attempts())``."""
        return [s.to_route_attempts_row() for s in self.source_summaries]

    def to_text(self) -> str:
        lines = [
            f"Run ID: {self.run_id}",
            f"Mode: {self.mode}",
            "",
            f"Routes requested: {self.routes_requested}",
            f"Routes successful: {self.routes_successful}",
            f"Routes failed: {self.routes_failed}",
            f"Observations collected: {self.observations_collected}",
            "",
            "Source results:",
            "",
        ]
        for s in self.source_summaries:
            lines.append(s.source)
            lines.append(f"  requested: {s.routes_requested}")
            lines.append(f"  successful: {s.routes_successful}")
            lines.append(f"  failed: {s.routes_failed}")
            lines.append(f"  observations: {s.observations_collected}")
            if s.failure_breakdown:
                lines.append(f"  failure breakdown: {s.failure_breakdown}")
            lines.append("")
        if self.failure_reasons:
            lines.append("Failure reasons (all sources):")
            for reason, count in sorted(self.failure_reasons.items()):
                lines.append(f"  {reason}: {count}")
        return "\n".join(lines)
