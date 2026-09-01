import json

import pytest

from scraper.models import ScrapeRunReport
from scraper.storage import write_raw_run, write_run_report, write_validated_run


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
