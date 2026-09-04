"""One-off: import the existing flat-file fare data into Postgres.

Reads every data/raw/fares/*.jsonl and data/validated/fares/*.jsonl file
(the real SerpApi run plus the archived mock run) and data/scraper_runs/*.json,
and inserts them into the fare_observations / scraper_runs tables via
src/engine/db.py. Idempotent -- safe to re-run; existing rows are left
alone (ON CONFLICT DO NOTHING on the observation_id/tree/run_id key).

Run from the repo root: DATABASE_URL=... python migrate_flat_files_to_postgres.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.engine import db

REPO_ROOT = Path(__file__).parent


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> None:
    assert db.is_configured(), "DATABASE_URL not set -- see .env.example"
    db.init_schema()

    total_raw = total_validated = total_runs = 0

    for path in sorted((REPO_ROOT / "data" / "raw" / "fares").glob("*.jsonl")):
        run_id = path.stem
        records = _read_jsonl(path)
        inserted = db.insert_observations(records, tree=db.TREE_RAW, run_id=run_id)
        total_raw += inserted
        print(f"  raw/{path.name}: {len(records)} records, {inserted} newly inserted")

    for path in sorted((REPO_ROOT / "data" / "validated" / "fares").glob("*.jsonl")):
        run_id = path.stem
        records = _read_jsonl(path)
        inserted = db.insert_observations(records, tree=db.TREE_VALIDATED, run_id=run_id)
        total_validated += inserted
        print(f"  validated/{path.name}: {len(records)} records, {inserted} newly inserted")

    for path in sorted((REPO_ROOT / "data" / "scraper_runs").glob("*.json")):
        run_id = path.stem
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        db.insert_run_report(run_id, report)
        total_runs += 1
        print(f"  scraper_runs/{path.name}: recorded")

    print(f"\nDone. raw={total_raw} validated={total_validated} runs={total_runs}")


if __name__ == "__main__":
    main()
