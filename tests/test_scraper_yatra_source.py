"""Tests for the Yatra adapter's pure-logic pieces (response mapping,
block detection). Deliberately does NOT launch a real browser or hit
yatra.com -- see module docstring in yatra_source.py for why a live run
is a manual/integration check, not part of this suite."""

from datetime import date
from types import SimpleNamespace

import pytest

from scraper.source import SearchRequest
from scraper.yatra_source import YatraSource, _departure_day_aria_label


def _request():
    return SearchRequest(origin="DEL", destination="BLR", flight_date=date(2026, 9, 20), booking_date=date(2026, 9, 2))


def test_source_name_is_yatra():
    assert YatraSource().name == "Yatra"


# --- _to_result: response mapping against the REAL verified schema ---
# Real response captured during recon (2026-09-02):
#   {"ld": "2026-10-27", "la": "QP", "lf": 7704, "isError": false,
#    "day": {"2026-09-02": {"lf": 8491, "la": "6E"}, ...}}

def _payload(day_entries: dict):
    return {"ld": "2026-10-27", "la": "QP", "lf": 7704, "isError": False, "day": day_entries}


def test_to_result_maps_real_schema_to_success():
    payload = _payload({"2026-09-20": {"lf": 9286, "la": "6E"}})
    result = YatraSource()._to_result(payload, _request())
    assert result.status == "SUCCESS"
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs.airline == "IndiGo"  # 6E mapped
    assert obs.total_fare == 9286.0
    assert obs.currency == "INR"
    assert obs.source == "yatra"


def test_to_result_tags_observations_as_lowest_of_day():
    # Critical: this source only ever gives the cheapest fare per day,
    # never the full spread -- must never look identical to a full
    # per-flight listing source downstream.
    payload = _payload({"2026-09-20": {"lf": 9286, "la": "6E"}})
    result = YatraSource()._to_result(payload, _request())
    assert result.observations[0].fare_type == "LOWEST_OF_DAY"


def test_to_result_unmapped_iata_code_falls_through_to_raw_code_not_guessed_name():
    # "HR" appeared in real recon data with no confirmed airline mapping.
    payload = _payload({"2026-09-20": {"lf": 22809, "la": "HR"}})
    result = YatraSource()._to_result(payload, _request())
    assert result.status == "SUCCESS"
    assert result.observations[0].airline == "HR"  # not fabricated as a real name


def test_to_result_date_not_present_in_calendar_is_empty_result():
    payload = _payload({"2026-09-21": {"lf": 8828, "la": "IX"}})  # missing our requested date
    result = YatraSource()._to_result(payload, _request())
    assert result.status == "EMPTY_RESULT"
    assert result.observations == []


def test_to_result_genuinely_empty_day_entry_is_empty_result_not_zero_fare():
    # Real recon data included {} for at least one date (2027-03-13) --
    # must never become total_fare=0.
    payload = _payload({"2026-09-20": {}})
    result = YatraSource()._to_result(payload, _request())
    assert result.status == "EMPTY_RESULT"
    assert result.observations == []


def test_to_result_missing_day_key_entirely_is_malformed_response():
    result = YatraSource()._to_result({"ld": "2026-10-27", "la": "QP", "lf": 7704}, _request())
    assert result.status == "MALFORMED_RESPONSE"


def test_to_result_day_not_a_dict_is_malformed_response():
    result = YatraSource()._to_result({"day": "not-a-dict"}, _request())
    assert result.status == "MALFORMED_RESPONSE"


def test_to_result_entry_missing_lf_or_la_is_parse_error_not_fabrication():
    payload = _payload({"2026-09-20": {"la": "6E"}})  # lf missing
    result = YatraSource()._to_result(payload, _request())
    assert result.status == "PARSE_ERROR"
    assert result.observations == []


def test_to_result_never_produces_non_inr_currency():
    payload = _payload({"2026-09-20": {"lf": 9286, "la": "6E"}})
    result = YatraSource()._to_result(payload, _request())
    assert all(obs.currency == "INR" for obs in result.observations)


def test_to_result_preserves_requested_route_and_dates():
    req = _request()
    payload = _payload({req.flight_date.isoformat(): {"lf": 9286, "la": "6E"}})
    result = YatraSource()._to_result(payload, req)
    obs = result.observations[0]
    assert obs.origin == req.origin
    assert obs.destination == req.destination
    assert obs.flight_date == req.flight_date.isoformat()
    assert obs.booking_date == req.booking_date.isoformat()


def test_to_result_uses_the_flight_date_specific_entry_not_the_calendar_wide_lowest():
    # payload's top-level "lf"/"la" (7704/QP on 2026-10-27) is the lowest
    # across the WHOLE calendar -- must not be confused with the specific
    # date this request actually asked about.
    req = _request()  # flight_date = 2026-09-20 per _request()
    payload = _payload({req.flight_date.isoformat(): {"lf": 9286, "la": "6E"}})
    result = YatraSource()._to_result(payload, req)
    assert result.observations[0].total_fare == 9286.0
    assert result.observations[0].airline == "IndiGo"


# --- _looks_blocked: best-effort CAPTCHA/challenge detection ---

def test_looks_blocked_detects_known_markers():
    for marker_title in ["Access Denied", "Are You a Human?", "Please complete the CAPTCHA", "Reference #18.abc"]:
        page = SimpleNamespace(title=lambda t=marker_title: t)
        assert YatraSource._looks_blocked(page) is True


def test_looks_blocked_false_for_normal_page_title():
    page = SimpleNamespace(title=lambda: "Yatra.com: Book Cheap Flights, Hotels, Bus & Holiday Packages")
    assert YatraSource._looks_blocked(page) is False


def test_looks_blocked_does_not_raise_if_title_unavailable():
    def _raise():
        raise RuntimeError("page closed")

    page = SimpleNamespace(title=_raise)
    assert YatraSource._looks_blocked(page) is False


# --- search_fares: missing playwright dependency is handled gracefully ---

def test_search_fares_reports_source_unavailable_if_playwright_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("simulated missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    result = YatraSource().search_fares(_request())
    assert result.status == "SOURCE_UNAVAILABLE"
    assert "playwright" in result.error_detail.lower()
    assert result.observations == []


# --- _departure_day_aria_label: must exactly match react-datepicker's ---
# --- real markup, verified against a captured day cell during recon  ---

def test_departure_day_aria_label_matches_captured_real_example():
    # Verbatim match against the actual DOM captured during recon:
    # aria-label="Choose Tuesday, September 15th, 2026" for 2026-09-15.
    assert _departure_day_aria_label(date(2026, 9, 15)) == "Choose Tuesday, September 15th, 2026"


@pytest.mark.parametrize(
    "day, expected_suffix",
    [(1, "st"), (2, "nd"), (3, "rd"), (4, "th"), (11, "th"), (12, "th"), (13, "th"), (21, "st"), (22, "nd"), (23, "rd"), (31, "st")],
)
def test_departure_day_aria_label_ordinal_suffixes(day, expected_suffix):
    # 11th/12th/13th are the classic trap for naive "last digit" ordinal
    # logic -- must be "th", not "st"/"nd"/"rd".
    label = _departure_day_aria_label(date(2026, 10, day))
    assert f"{day}{expected_suffix}," in label


def test_departure_day_aria_label_uses_english_names_regardless_of_locale():
    label = _departure_day_aria_label(date(2026, 12, 25))
    assert "December" in label
    assert "Friday" in label  # 2026-12-25 is a Friday
