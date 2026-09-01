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
from typing import Any, Dict, List

from .models import ScrapeRunReport


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
