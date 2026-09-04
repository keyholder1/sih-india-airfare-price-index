"""Tests for the poll-driven step executor in api/services/scrape_job_service.py.

These cover the step-machine logic itself (which step runs when, what
advances the job and what doesn't, failure handling) by stubbing out
Postgres (``db``), the live scraper call (``_scrape``), and the
statistics recompute (``_recompute_and_summarize``) -- not by hitting a
real database or SerpApi. The underlying statistics engine
(AirfareAnalytics, data_quality.validate_fare_batch) already has its own
coverage elsewhere (test_analytics.py, test_data_quality.py,
test_integration_data_quality_index.py); these tests are about the new
step-execution behavior only.
"""

from __future__ import annotations

import types

import pytest

from api.services import scrape_job_service as svc
from src.engine import db


class FakeDB:
    """In-memory stand-in for the handful of ``db`` functions the step
    executor calls -- enough to drive the state machine without Postgres."""

    def __init__(self, **job_state):
        self.job = {
            "origin": "BLR",
            "destination": "DEL",
            "status": db.JOB_QUEUED,
            "step": 0,
            "pending_dates": None,
            "result": None,
            **job_state,
        }
        self.calls = []
        self.existing_validated_count = 0
        self.inserted = []

    # --- read side ---
    def get_job_step_state(self, job_id):
        return dict(self.job)

    def get_job(self, job_id):
        return dict(self.job)

    def count_observations_for_route(self, origin, destination, tree):
        return self.existing_validated_count

    def get_observations_for_run(self, run_id, tree):
        return self.inserted

    # --- write side ---
    def insert_observations(self, observations, tree, run_id):
        self.inserted.extend(observations)
        return len(observations)

    def insert_run_report(self, run_id, report):
        self.calls.append(("insert_run_report", run_id, report))

    def advance_job(self, job_id, step, status, message=None, result=None, error=None):
        self.job["step"] = step
        self.job["status"] = status
        if result is not None:
            self.job["result"] = result
        self.calls.append(("advance_job", step, status))

    def update_job(self, job_id, status, message=None, result=None, error=None):
        self.job["status"] = status
        if result is not None:
            self.job["result"] = result
        if error is not None:
            self.job["error"] = error
        self.calls.append(("update_job", status, error))


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDB()
    for name in (
        "get_job_step_state",
        "get_job",
        "count_observations_for_route",
        "get_observations_for_run",
        "insert_observations",
        "insert_run_report",
        "advance_job",
        "update_job",
    ):
        monkeypatch.setattr(svc.db, name, getattr(fake, name))
    # Real constants (JOB_DONE etc.) stay as-is on svc.db -- only the
    # functions above are stubbed.
    return fake


def test_cache_hit_walks_the_same_pills_as_a_fresh_run_before_finishing(fake_db, monkeypatch):
    fake_db.existing_validated_count = 3
    monkeypatch.setattr(
        svc, "_recompute_and_summarize",
        lambda origin, destination, from_cache, quality_fields=None: {"from_cache": from_cache, "route": f"{origin}-{destination}"},
    )

    # Poll 1: cache check -- doesn't finish in one step, moves to a
    # visible "Scraping" pill first (see STEP_CACHE_VERIFY's docstring).
    svc.advance_job("job-1")
    assert fake_db.job["status"] == db.JOB_SCRAPING
    assert fake_db.job["step"] == svc.STEP_CACHE_VERIFY
    assert fake_db.job["result"] is None  # not done yet -- no result to show

    # Poll 2: Data Quality pill.
    svc.advance_job("job-1")
    assert fake_db.job["status"] == db.JOB_VALIDATING
    assert fake_db.job["step"] == svc.STEP_CACHE_VALIDATED

    # Poll 3: Index Engine pill.
    svc.advance_job("job-1")
    assert fake_db.job["status"] == db.JOB_INDEXING
    assert fake_db.job["step"] == svc.STEP_CACHE_INDEXED

    # Poll 4: actually finishes.
    svc.advance_job("job-1")
    assert fake_db.job["status"] == db.JOB_DONE
    assert fake_db.job["result"]["from_cache"] is True


def test_cache_miss_transitions_to_scraping_without_scraping_yet(fake_db, monkeypatch):
    fake_db.existing_validated_count = 0
    scrape_called = []
    monkeypatch.setattr(svc, "_scrape", lambda *a, **k: scrape_called.append(1) or ([], None))

    svc.advance_job("job-1")

    assert fake_db.job["status"] == db.JOB_SCRAPING
    assert fake_db.job["step"] == 0
    assert scrape_called == []  # the first poll only decides the path, doesn't scrape yet


def test_each_scraping_poll_does_exactly_one_date(fake_db, monkeypatch):
    fake_db.job["status"] = db.JOB_SCRAPING
    fake_db.job["step"] = 2
    fake_db.job["pending_dates"] = [["2026-01-01", "2026-01-01"]] * svc.N_DATE_STEPS

    scrape_calls = []

    def fake_scrape(origin, destination, dates):
        scrape_calls.append(dates)
        return ([{"observation_id": "x", "origin": origin, "destination": destination}], None)

    monkeypatch.setattr(svc, "_scrape", fake_scrape)

    svc.advance_job("job-1")

    assert len(scrape_calls) == 1
    assert len(scrape_calls[0]) == 1  # exactly one date pair per poll
    assert fake_db.job["step"] == 3
    assert fake_db.job["status"] == db.JOB_SCRAPING
    assert len(fake_db.inserted) == 1


def test_final_date_step_advances_to_validate_stage(fake_db, monkeypatch):
    fake_db.job["status"] = db.JOB_SCRAPING
    fake_db.job["step"] = svc.N_DATE_STEPS - 1
    fake_db.job["pending_dates"] = [["2026-01-01", "2026-01-01"]] * svc.N_DATE_STEPS
    monkeypatch.setattr(svc, "_scrape", lambda *a, **k: ([], None))

    svc.advance_job("job-1")

    assert fake_db.job["step"] == svc.N_DATE_STEPS


def test_validate_step_fails_job_when_nothing_was_collected(fake_db):
    fake_db.job["status"] = db.JOB_SCRAPING
    fake_db.job["step"] = svc.N_DATE_STEPS
    fake_db.inserted = []

    svc.advance_job("job-1")

    assert fake_db.job["status"] == db.JOB_FAILED


def test_validate_step_persists_quality_fields_for_next_step(fake_db, monkeypatch):
    fake_db.job["status"] = db.JOB_SCRAPING
    fake_db.job["step"] = svc.N_DATE_STEPS
    fake_db.inserted = [{"observation_id": "x", "origin": "BLR", "destination": "DEL"}]

    fake_quality_result = types.SimpleNamespace(
        records_received=1,
        records_valid=1,
        records_flagged=0,
        records_rejected=0,
        rejection_reasons={},
        quality_score=95.0,
        quality_grade="A",
        valid_observations=[{"observation_id": "x"}],
    )
    monkeypatch.setattr(svc.data_quality_mod, "validate_fare_batch", lambda obs: fake_quality_result)

    svc.advance_job("job-1")

    assert fake_db.job["status"] == db.JOB_INDEXING
    assert fake_db.job["step"] == svc.STEP_VALIDATE
    assert fake_db.job["result"]["quality_score"] == 95.0
    assert fake_db.job["result"]["quality_grade"] == "A"


def test_recompute_step_merges_prior_quality_fields_and_finishes(fake_db, monkeypatch):
    fake_db.job["status"] = db.JOB_INDEXING
    fake_db.job["step"] = svc.STEP_VALIDATE
    fake_db.job["result"] = {"quality_score": 95.0, "quality_grade": "A"}

    captured = {}

    def fake_recompute(origin, destination, from_cache, quality_fields=None):
        captured["quality_fields"] = quality_fields
        return {"route": f"{origin}-{destination}", "from_cache": from_cache}

    monkeypatch.setattr(svc, "_recompute_and_summarize", fake_recompute)

    svc.advance_job("job-1")

    assert fake_db.job["status"] == db.JOB_DONE
    assert captured["quality_fields"] == {"quality_score": 95.0, "quality_grade": "A"}


def test_a_failing_step_does_not_advance_and_marks_job_failed(fake_db, monkeypatch):
    fake_db.job["status"] = db.JOB_SCRAPING
    fake_db.job["step"] = 0
    fake_db.job["pending_dates"] = [["2026-01-01", "2026-01-01"]] * svc.N_DATE_STEPS

    def boom(*a, **k):
        raise RuntimeError("SerpApi exploded")

    monkeypatch.setattr(svc, "_scrape", boom)

    svc.advance_job("job-1")

    assert fake_db.job["status"] == db.JOB_FAILED
    assert fake_db.job["step"] == 0  # unchanged -- the next poll retries this exact step


def test_terminal_job_is_a_no_op(fake_db):
    fake_db.job["status"] = db.JOB_DONE
    fake_db.job["step"] = svc.STEP_RECOMPUTE

    svc.advance_job("job-1")

    assert fake_db.calls == []


def test_start_job_reuses_an_existing_active_job(monkeypatch):
    monkeypatch.setattr(svc.db, "find_active_job", lambda origin, destination: "existing-job-id")

    created = []
    monkeypatch.setattr(svc.db, "create_job", lambda *a, **k: created.append(1) or "new-job-id")
    monkeypatch.setattr(svc.db, "is_configured", lambda: True)

    import asyncio

    job_id = asyncio.run(svc.start_job("BLR", "DEL"))

    assert job_id == "existing-job-id"
    assert created == []


def test_start_job_rejects_same_origin_and_destination(monkeypatch):
    monkeypatch.setattr(svc.db, "is_configured", lambda: True)
    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(svc.start_job("BLR", "blr"))
