"""IndiGo adapter scaffold — deliberately no network I/O. Proves the
credential-gating behaviour, not any real API call (none exists yet)."""

from datetime import date

import pytest

from scraper.indigo_source import IndiGoCredentials, IndiGoSource, load_credentials_from_env
from scraper.source import SearchRequest


def _request():
    return SearchRequest(origin="BLR", destination="DEL", flight_date=date(2026, 9, 15), booking_date=date(2026, 9, 1))


def test_missing_credentials_returns_source_unavailable_not_a_crash():
    source = IndiGoSource(credentials=None)
    result = source.search_fares(_request())
    assert result.status == "SOURCE_UNAVAILABLE"
    assert result.observations == []
    assert "INDIGO_API_KEY" in result.error_detail


def test_never_raises_for_missing_credentials():
    source = IndiGoSource(credentials=None)
    # Must not raise — SearchRequest is well-formed, credentials being
    # absent is an ordinary "can't use this source" outcome.
    source.search_fares(_request())


def test_present_but_incomplete_call_logic_still_returns_source_unavailable_not_fake_success():
    # Credentials ARE configured, but _call_api is intentionally
    # unimplemented (no verified IndiGo API contract exists yet) — this
    # must never look like a successful call.
    creds = IndiGoCredentials(api_key="test-key-not-real")
    source = IndiGoSource(credentials=creds)
    result = source.search_fares(_request())
    assert result.status == "SOURCE_UNAVAILABLE"
    assert result.observations == []
    assert "verified" in result.error_detail.lower() or "contract" in result.error_detail.lower()


def test_load_credentials_from_env_returns_none_when_api_key_absent(monkeypatch):
    monkeypatch.delenv("INDIGO_API_KEY", raising=False)
    assert load_credentials_from_env() is None


def test_load_credentials_from_env_reads_api_key(monkeypatch):
    monkeypatch.setenv("INDIGO_API_KEY", "fake-test-value")
    monkeypatch.delenv("INDIGO_USERNAME", raising=False)
    creds = load_credentials_from_env()
    assert creds is not None
    assert creds.api_key == "fake-test-value"
    assert creds.username is None


def test_source_name_is_indigo():
    assert IndiGoSource(credentials=None).name == "IndiGo"


def test_never_fabricates_an_observation_regardless_of_credential_state():
    # Whether credentials are present or absent, no code path in this
    # adapter today can produce an observation — see module docstring.
    for creds in (None, IndiGoCredentials(api_key="fake")):
        result = IndiGoSource(credentials=creds).search_fares(_request())
        assert result.observations == []
