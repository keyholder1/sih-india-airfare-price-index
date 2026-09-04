"""PostgreSQL-backed storage for fare observations, scraper runs, and
on-demand scrape jobs.

Replaces the flat-file trees ``data/raw/fares/*.jsonl`` and
``data/validated/fares/*.jsonl`` as the source of truth for
``data_access.load_validated_observations`` / ``load_raw_observations``.
The physical raw-vs-validated separation those files existed to enforce
("nobody can accidentally point the index engine at unvalidated scraper
output by reusing a path" -- see scraper/storage.py) is preserved here as
a ``tree`` column, filtered explicitly on every read -- there is no
unfiltered query path that could blend the two.

Connection is read from ``DATABASE_URL`` (e.g.
``postgresql://sih:sih_dev_password@localhost:5434/airfare_index``). A
missing/unreachable database is not fatal to the rest of the app: callers
fall back to the same synthetic demo behavior data_access.py already had
before this module existed (see ``data_access.load_validated_observations``),
so a judge running this without a database still sees an honestly-labelled
demo, never a crash.
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

import psycopg2
import psycopg2.extras

ENV_DATABASE_URL = "DATABASE_URL"

TREE_RAW = "raw"
TREE_VALIDATED = "validated"

JOB_QUEUED = "queued"
JOB_SCRAPING = "scraping"
JOB_VALIDATING = "validating"
JOB_INDEXING = "indexing"
JOB_DONE = "done"
JOB_FAILED = "failed"


def database_url() -> Optional[str]:
    return os.environ.get(ENV_DATABASE_URL)


def is_configured() -> bool:
    return bool(database_url())


@contextmanager
def _connect():
    url = database_url()
    if not url:
        raise RuntimeError(
            f"{ENV_DATABASE_URL} is not set -- see .env.example. "
            "Callers should check db.is_configured() before calling into this module."
        )
    conn = psycopg2.connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS fare_observations (
    id BIGSERIAL PRIMARY KEY,
    observation_id TEXT NOT NULL,
    tree TEXT NOT NULL CHECK (tree IN ('raw', 'validated')),
    run_id TEXT NOT NULL,
    airline TEXT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    flight_date DATE,
    booking_date DATE,
    total_fare NUMERIC,
    currency TEXT,
    source TEXT,
    is_mock BOOLEAN NOT NULL DEFAULT TRUE,
    record JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (observation_id, tree, run_id)
);
CREATE INDEX IF NOT EXISTS ix_fare_observations_tree_route ON fare_observations (tree, origin, destination);
CREATE INDEX IF NOT EXISTS ix_fare_observations_tree_date ON fare_observations (tree, flight_date);
CREATE INDEX IF NOT EXISTS ix_fare_observations_run ON fare_observations (run_id);

CREATE TABLE IF NOT EXISTS scraper_runs (
    run_id TEXT PRIMARY KEY,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scrape_jobs (
    id UUID PRIMARY KEY,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    message TEXT,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_article_cache (
    cache_key TEXT PRIMARY KEY,
    articles JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def init_schema() -> None:
    """Idempotent -- safe to call on every app startup."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


def _row_to_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """The stored JSONB `record` is the original observation dict
    (matching data_contract.md's shape) -- returned as-is, never
    reconstructed from the flattened columns, so nothing is lost or
    silently coerced by the column typing."""
    record = dict(row["record"])
    record["is_mock"] = row["is_mock"]
    return record


def load_observations(tree: str) -> List[Dict[str, Any]]:
    """All observations for one tree ('raw' or 'validated'), across every
    run -- the Postgres equivalent of concatenating every .jsonl file in
    that tree. Raises if `tree` isn't one of the two known values, same
    as the CHECK constraint enforces at the database level."""
    if tree not in (TREE_RAW, TREE_VALIDATED):
        raise ValueError(f"Unknown tree {tree!r}; must be {TREE_RAW!r} or {TREE_VALIDATED!r}")
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT record, is_mock FROM fare_observations WHERE tree = %s", (tree,))
            rows = cur.fetchall()
    return [_row_to_record(r) for r in rows]


def count_observations_for_route(origin: str, destination: str, tree: str = TREE_VALIDATED) -> int:
    """How many observations already exist for this exact route -- used
    by the on-demand scrape pipeline to decide whether a fresh live
    SerpApi call is actually needed, or whether previously-recorded real
    data for this route already exists and can be shown immediately
    instead of spending real API quota and the viewer's time on a
    redundant call."""
    if tree not in (TREE_RAW, TREE_VALIDATED):
        raise ValueError(f"Unknown tree {tree!r}; must be {TREE_RAW!r} or {TREE_VALIDATED!r}")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM fare_observations WHERE tree = %s AND origin = %s AND destination = %s",
                (tree, origin, destination),
            )
            (count,) = cur.fetchone()
    return int(count)


def get_route_fares(origin: str, destination: str, tree: str = TREE_VALIDATED) -> List[Dict[str, Any]]:
    """Flattened (not the full JSONB record) fare rows for one route --
    used to show the viewer the actual collected prices behind a route
    lookup, not just the computed index number. Cheapest first, so a
    capped display naturally shows the most useful rows."""
    if tree not in (TREE_RAW, TREE_VALIDATED):
        raise ValueError(f"Unknown tree {tree!r}; must be {TREE_RAW!r} or {TREE_VALIDATED!r}")
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT airline, flight_date, booking_date, total_fare, currency, source "
                "FROM fare_observations WHERE tree = %s AND origin = %s AND destination = %s "
                "AND total_fare IS NOT NULL ORDER BY total_fare ASC",
                (tree, origin, destination),
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("flight_date") is not None:
            d["flight_date"] = d["flight_date"].isoformat()
        if d.get("booking_date") is not None:
            d["booking_date"] = d["booking_date"].isoformat()
        if d.get("total_fare") is not None:
            d["total_fare"] = float(d["total_fare"])
        out.append(d)
    return out


def insert_observations(observations: List[Dict[str, Any]], tree: str, run_id: str) -> int:
    """Insert observations into one tree for one run. Idempotent per
    (observation_id, tree, run_id): re-inserting the same run is a no-op
    via ON CONFLICT DO NOTHING, not a duplicate -- mirrors the exclusive-
    create-then-refuse-to-overwrite safety scraper/storage.py's flat-file
    writers already had. Returns the number of rows actually inserted."""
    if tree not in (TREE_RAW, TREE_VALIDATED):
        raise ValueError(f"Unknown tree {tree!r}; must be {TREE_RAW!r} or {TREE_VALIDATED!r}")
    if not observations:
        return 0

    rows = []
    for obs in observations:
        rows.append(
            (
                str(obs.get("observation_id")),
                tree,
                run_id,
                obs.get("airline"),
                obs.get("origin"),
                obs.get("destination"),
                obs.get("flight_date"),
                obs.get("booking_date"),
                obs.get("total_fare"),
                obs.get("currency"),
                obs.get("source"),
                bool(obs.get("is_mock", True)),
                json.dumps(obs, default=str),
            )
        )

    with _connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO fare_observations
                    (observation_id, tree, run_id, airline, origin, destination,
                     flight_date, booking_date, total_fare, currency, source, is_mock, record)
                VALUES %s
                ON CONFLICT (observation_id, tree, run_id) DO NOTHING
                """,
                rows,
            )
            inserted = cur.rowcount
    return inserted


def insert_run_report(run_id: str, report: Dict[str, Any]) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scraper_runs (run_id, report) VALUES (%s, %s) "
                "ON CONFLICT (run_id) DO UPDATE SET report = EXCLUDED.report",
                (run_id, json.dumps(report, default=str)),
            )


# --- News article cache ------------------------------------------------------
# One row per (route/query, calendar week) -- see index_engine.news_provider's
# NewsSearchQuery. Deliberately caches the *search results* (candidate
# articles), not the final ranked matches: re-running the ranking against
# the current route movement is free/local, so caching only guards the
# actual external API calls (newsdata.io, NewsAPI.org, Event Registry,
# ...), which are what a real key's quota is spent on. A cache miss on
# a never-configured DATABASE_URL just means "no cache" -- callers should
# check db.is_configured() first, same as everywhere else in this module.


def get_cached_news(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """Returns the cached article list for this key, or ``None`` on a
    cache miss (never an empty list for "not cached yet" vs "cached but
    genuinely found nothing" -- those are different outcomes)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT articles FROM news_article_cache WHERE cache_key = %s", (cache_key,))
            row = cur.fetchone()
    if row is None:
        return None
    return row[0]


def set_cached_news(cache_key: str, articles: List[Dict[str, Any]]) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO news_article_cache (cache_key, articles, fetched_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (cache_key) DO UPDATE SET articles = EXCLUDED.articles, fetched_at = now()",
                (cache_key, json.dumps(articles, default=str)),
            )


# --- On-demand scrape jobs --------------------------------------------------


def create_job(origin: str, destination: str) -> str:
    job_id = str(uuid.uuid4())
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_jobs (id, origin, destination, status, message) "
                "VALUES (%s, %s, %s, %s, %s)",
                (job_id, origin, destination, JOB_QUEUED, "Queued."),
            )
    return job_id


def update_job(
    job_id: str,
    status: str,
    message: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_jobs
                SET status = %s,
                    message = COALESCE(%s, message),
                    result = COALESCE(%s, result),
                    error = COALESCE(%s, error),
                    updated_at = now()
                WHERE id = %s
                """,
                (status, message, json.dumps(result, default=str) if result is not None else None, error, job_id),
            )


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Returns None for an unknown OR malformed job id (e.g. not a valid
    UUID) -- a caller-facing 404, not a database error. Validated here
    rather than left to Postgres's own UUID parsing, which raises instead
    of returning zero rows for a syntactically invalid input."""
    try:
        uuid.UUID(job_id)
    except (ValueError, AttributeError, TypeError):
        return None
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, origin, destination, status, message, result, error, "
                "created_at, updated_at FROM scrape_jobs WHERE id = %s",
                (job_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    out = dict(row)
    out["id"] = str(out["id"])
    out["created_at"] = out["created_at"].isoformat()
    out["updated_at"] = out["updated_at"].isoformat()
    return out
