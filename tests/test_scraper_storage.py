import json

import pytest

from scraper.models import ScrapeRunReport, SourceRunSummary
from scraper.storage import (
    build_collection_envelope,
    load_json_observations,
    write_collection_json,
    write_raw_run,
    write_run_report,
    write_validated_run,
)


def _report(run_id="run_test"):
    return ScrapeRunReport(
        run_id=run_id, mode="mock", started_at="2026-09-01T00:00:00Z", finished_at="2026-09-01T00:01:00Z",
        routes_requested=1, routes_successful=1, routes_failed=0, observations_collected=1,
    )


def test_write_raw_run_creates_file_under_raw_fares(tmp_path):
    path = write_raw_run("run_test", [{"observation_id": "A", "total_fare": 100}], base_dir=str(tmp_path))
    assert path == tmp_path / "raw" / "fares" / "run_test.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["observation_id"] == "A"


def test_write_validated_run_is_physically_separate_from_raw(tmp_path):
    raw_path = write_raw_run("run_test", [{"observation_id": "A"}], base_dir=str(tmp_path))
    validated_path = write_validated_run("run_test", [{"observation_id": "A"}], base_dir=str(tmp_path))
    assert raw_path != validated_path
    # Check the tree-root directory name directly (two levels up from the
    # file) rather than substring-searching the full path, since tmp_path
    # itself is derived from this test's name and could coincidentally
    # contain "validated".
    assert raw_path.parent.parent.name == "raw"
    assert validated_path.parent.parent.name == "validated"


def test_write_run_report_creates_json_under_scraper_runs(tmp_path):
    report = _report()
    path = write_run_report(report, base_dir=str(tmp_path))
    assert path == tmp_path / "scraper_runs" / "run_test.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_test"
    assert payload["routes_requested"] == 1


def test_raw_run_never_overwrites_a_previous_run(tmp_path):
    write_raw_run("run_dupe", [{"observation_id": "A"}], base_dir=str(tmp_path))
    with pytest.raises(FileExistsError):
        write_raw_run("run_dupe", [{"observation_id": "B"}], base_dir=str(tmp_path))
    # Original content is untouched.
    path = tmp_path / "raw" / "fares" / "run_dupe.jsonl"
    assert json.loads(path.read_text(encoding="utf-8").strip())["observation_id"] == "A"


def test_run_report_never_overwrites_a_previous_run(tmp_path):
    write_run_report(_report("run_dupe2"), base_dir=str(tmp_path))
    with pytest.raises(FileExistsError):
        write_run_report(_report("run_dupe2"), base_dir=str(tmp_path))


# --- JSON collection envelope (the primary team handoff format) ---

def _report_with_summary(run_id="run_json_test"):
    return ScrapeRunReport(
        run_id=run_id, mode="mock", started_at="2026-09-01T00:00:00Z", finished_at="2026-09-01T00:01:00Z",
        routes_requested=1, routes_successful=1, routes_failed=0, observations_collected=2,
        source_summaries=[
            SourceRunSummary(
                source="MockIndiGo", routes_requested=1, routes_successful=1, routes_failed=0,
                routes_attempted=["BLR-DEL"], observations_collected=2,
            )
        ],
    )


def _observations():
    return [
        {"observation_id": "A", "airline": "IndiGo", "origin": "BLR", "destination": "DEL",
         "flight_date": "2026-09-08", "booking_date": "2026-09-01", "total_fare": 5000.0, "currency": "INR"},
        {"observation_id": "B", "airline": "IndiGo", "origin": "BLR", "destination": "DEL",
         "flight_date": "2026-09-08", "booking_date": "2026-09-01", "total_fare": 5300.0, "currency": "INR"},
    ]


def test_build_collection_envelope_has_the_four_required_sections():
    envelope = build_collection_envelope(_report_with_summary(), _observations())
    assert envelope["schema_version"] == "1.0"
    assert "collection_metadata" in envelope
    assert "route_attempts" in envelope
    assert envelope["observations"] == _observations()


def test_build_collection_envelope_never_aggregates_observations():
    # Two individual fare quotes for the same route/date must remain two
    # separate observation objects, never collapsed into one route-level value.
    envelope = build_collection_envelope(_report_with_summary(), _observations())
    assert len(envelope["observations"]) == 2
    assert envelope["observations"][0]["observation_id"] != envelope["observations"][1]["observation_id"]


def test_build_collection_envelope_route_attempts_defaults_from_report():
    envelope = build_collection_envelope(_report_with_summary(), _observations())
    assert envelope["route_attempts"] == [
        {"source": "MockIndiGo", "routes_requested": 1, "routes_successful": 1,
         "routes_failed": 0, "routes_attempted": ["BLR-DEL"]}
    ]


def test_write_collection_json_creates_file_under_collections(tmp_path):
    path = write_collection_json(_report_with_summary(), _observations(), base_dir=str(tmp_path))
    assert path == tmp_path / "collections" / "run_json_test.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert len(payload["observations"]) == 2


def test_write_collection_json_never_overwrites_a_previous_run(tmp_path):
    write_collection_json(_report_with_summary("run_dupe3"), _observations(), base_dir=str(tmp_path))
    with pytest.raises(FileExistsError):
        write_collection_json(_report_with_summary("run_dupe3"), _observations(), base_dir=str(tmp_path))


def test_load_json_observations_returns_just_the_observations_list(tmp_path):
    path = write_collection_json(_report_with_summary(), _observations(), base_dir=str(tmp_path))
    loaded = load_json_observations(str(path))
    assert loaded == _observations()


def test_load_json_observations_raises_keyerror_on_malformed_file(tmp_path):
    bad_path = tmp_path / "not_a_collection.json"
    bad_path.write_text(json.dumps({"some_other_shape": True}), encoding="utf-8")
    with pytest.raises(KeyError):
        load_json_observations(str(bad_path))
