"""Raw-vs-validated storage, kept as two physically separate trees so
nobody can accidentally point the index engine at unvalidated scraper
output by reusing a path (see docs/scraper.md "Raw vs validated storage").

    data/
    +-- raw/fares/<run_id>.jsonl          (exactly what the scraper collected)
    +-- validated/fares/<run_id>.jsonl    (post data_quality, VALID+FLAGGED only)
    +-- scraper_runs/<run_id>.json        (the run report)

Every write is exclusive-create (fails loudly rather than overwriting) —
a run_id is timestamp-derived, so a collision means something is genuinely
wrong (e.g. a caller reusing an old run_id), not an expected retry path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import ScrapeRunReport

#: Schema version for the JSON collection envelope (see
#: build_collection_envelope / write_collection_json). Bump this if the
#: envelope's top-level shape ever changes in a way a consumer should
#: check for.
COLLECTION_SCHEMA_VERSION = "1.0"


def _write_jsonl_exclusive(path: Path, records: List[Dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, default=str) + "\n")
    return path


def write_raw_run(run_id: str, observations: List[Dict[str, Any]], base_dir: str = "data") -> Path:
    """Persist exactly what the scraper collected, unmodified."""
    path = Path(base_dir) / "raw" / "fares" / f"{run_id}.jsonl"
    return _write_jsonl_exclusive(path, observations)


def write_validated_run(run_id: str, valid_observations: List[Dict[str, Any]], base_dir: str = "data") -> Path:
    """Persist the ``data_quality.DataQualityResult.valid_observations``
    (VALID + FLAGGED, never REJECTED) for this run — physically separate
    from the raw tree so a consumer can never mistake one for the other."""
    path = Path(base_dir) / "validated" / "fares" / f"{run_id}.jsonl"
    return _write_jsonl_exclusive(path, valid_observations)


def write_run_report(report: ScrapeRunReport, base_dir: str = "data") -> Path:
    path = Path(base_dir) / "scraper_runs" / f"{report.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    return path


def build_collection_envelope(
    report: ScrapeRunReport,
    observations: List[Dict[str, Any]],
    route_attempts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the single-JSON team handoff envelope for one scrape run.

    This is the primary exchange format between this package and the rest
    of the team (docs/data_contract.md's ``observations`` shape, plus
    metadata a downstream consumer needs without a second file):

        {
          "schema_version": "1.0",
          "collection_metadata": {...},   # from ScrapeRunReport, flattened
          "route_attempts": [...],        # report.to_route_attempts() by default
          "observations": [...]           # one object per fare quote, never aggregated
        }

    ``observations`` must already be one dict per individual fare
    observation (e.g. ``run_scrape(...)``'s first return value, or
    anything shaped like ``RawFareObservation.to_record()``) -- this
    function never aggregates or collapses records; that would lose the
    per-quote granularity the index engine's representative-fare
    statistics (median/mean/trimmed-mean) depend on.

    ``route_attempts`` defaults to ``report.to_route_attempts()`` (shaped
    exactly as ``data_quality.health`` expects) if not supplied
    separately.
    """
    return {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "collection_metadata": report.to_dict(),
        "route_attempts": route_attempts if route_attempts is not None else report.to_route_attempts(),
        "observations": observations,
    }


def write_collection_json(
    report: ScrapeRunReport,
    observations: List[Dict[str, Any]],
    route_attempts: Optional[List[Dict[str, Any]]] = None,
    base_dir: str = "data",
) -> Path:
    """Write the single-JSON team handoff envelope for one run.

    Physically separate from the raw/validated ``.jsonl`` trees (see
    module docstring) -- this is the file to hand to another teammate or
    load with ``load_json_observations``; the ``.jsonl`` trees remain an
    internal raw-vs-validated audit trail, not the primary interchange
    format.

    Written to ``<base_dir>/collections/<run_id>.json``. Exclusive-create,
    same as every other writer in this module -- a duplicate ``run_id``
    raises ``FileExistsError`` rather than silently overwriting a
    previous run.
    """
    envelope = build_collection_envelope(report, observations, route_attempts)
    path = Path(base_dir) / "collections" / f"{report.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, default=str)
    return path


def load_json_observations(path: str) -> List[Dict[str, Any]]:
    """Load a collection JSON envelope and return just its
    ``observations`` list -- ready to pass straight into
    ``data_quality.validate_fare_batch(raw_data=...)`` as ``raw_data``.

    Raises ``KeyError`` if the file doesn't have an ``observations`` key
    (i.e. isn't actually a collection envelope) rather than silently
    returning an empty list, since that would hide a real integration
    mistake from whoever's consuming this.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["observations"]
