"""Tests for the SerpApi source adapter. Uses a fake httpx-like client
injected via the constructor -- no real network calls, no real API key.
Payload shapes are trimmed-down versions of a REAL response captured
during this project's recon (DEL->BLR, 2026-09-10)."""

from datetime import date

import httpx
import pytest

from scraper.serpapi_source import SerpApiCredentials, SerpApiSource, load_credentials_from_env
from scraper.source import SearchRequest


def _request():
    return SearchRequest(origin="DEL", destination="BLR", flight_date=date(2026, 9, 10), booking_date=date(2026, 9, 2))


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("no json configured on fake response")
        return self._json_data


class _FakeClient:
    """Stands in for httpx.Client -- .get() returns whatever was configured,
    or raises whatever exception was configured, ignoring the real URL."""

    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.last_params = None

    def get(self, url, params=None):
        self.last_params = params
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response

    def close(self):
        pass


# --- credential handling ---

def test_missing_credentials_returns_source_unavailable():
    source = SerpApiSource(credentials=None, client=_FakeClient())
    result = source.search_fares(_request())
    assert result.status == "SOURCE_UNAVAILABLE"
    assert "SERPAPI_API_KEY" in result.error_detail
    assert result.observations == []


def test_load_credentials_from_env_returns_none_when_absent(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    assert load_credentials_from_env() is None


def test_load_credentials_from_env_reads_key(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "fake-test-key")
    creds = load_credentials_from_env()
    assert creds is not None
    assert creds.api_key == "fake-test-key"


# --- real captured response shape (trimmed) ---

def _real_shaped_payload():
    # Trimmed from the actual recon capture -- one direct itinerary, one
    # connecting itinerary, matching the real field names/nesting exactly.
    return {
        "search_parameters": {"currency": "INR"},
        "best_flights": [
            {
                "flights": [
                    {
                        "departure_airport": {"id": "DEL", "time": "2026-09-10 12:20"},
                        "arrival_airport": {"id": "BLR", "time": "2026-09-10 15:20"},
                        "airline": "IndiGo",
                        "flight_number": "6E 850",
                    }
                ],
                "total_duration": 180,
                "price": 8724,
                "type": "One way",
                "booking_token": "TOKEN_ABC",
            }
        ],
        "other_flights": [
            {
                "flights": [
                    {
                        "departure_airport": {"id": "DEL", "time": "2026-09-10 16:30"},
                        "arrival_airport": {"id": "NAG", "time": "2026-09-10 18:15"},
                        "airline": "IndiGo",
                        "flight_number": "6E 6433",
                    },
                    {
                        "departure_airport": {"id": "NAG", "time": "2026-09-10 19:35"},
                        "arrival_airport": {"id": "BLR", "time": "2026-09-10 21:20"},
                        "airline": "IndiGo",
                        "flight_number": "6E 6432",
                    },
                ],
                "total_duration": 290,
                "price": 8176,  # ONE price for the whole 2-leg connection
                "type": "One way",
                "booking_token": "TOKEN_XYZ",
            }
        ],
    }


def test_real_shaped_payload_maps_to_success_with_two_observations():
    client = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    source = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client)
    result = source.search_fares(_request())
    assert result.status == "SUCCESS"
    assert len(result.observations) == 2


def test_direct_itinerary_maps_correctly():
    client = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    direct = next(o for o in result.observations if o.stops == 0)
    assert direct.airline == "IndiGo"
    assert direct.total_fare == 8724.0
    assert direct.currency == "INR"
    assert direct.origin == "DEL"
    assert direct.destination == "BLR"
    assert direct.flight_date == "2026-09-10"
    assert direct.duration == 180
    assert direct.source == "serpapi_google_flights"


def test_connecting_itinerary_uses_one_price_for_whole_itinerary_not_per_leg():
    # The critical mapping rule: a 2-leg connection has ONE price in the
    # real API, covering both legs -- must not be split or doubled.
    client = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    connecting = next(o for o in result.observations if o.stops == 1)
    assert connecting.total_fare == 8176.0
    assert connecting.stops == 1
    assert connecting.duration == 290


def test_observation_ids_use_booking_token_when_present_and_are_distinct():
    client = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    ids = [o.observation_id for o in result.observations]
    assert len(ids) == len(set(ids))
    assert any("TOKEN_ABC" in i for i in ids)
    assert any("TOKEN_XYZ" in i for i in ids)


def test_currency_is_always_inr_regardless_of_response_content():
    client = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert all(o.currency == "INR" for o in result.observations)


def test_request_params_include_inr_and_one_way_type():
    client = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert client.last_params["currency"] == "INR"
    assert client.last_params["type"] == "2"
    assert client.last_params["departure_id"] == "DEL"
    assert client.last_params["arrival_id"] == "BLR"
    assert client.last_params["outbound_date"] == "2026-09-10"


# --- error handling ---

def test_serpapi_error_key_is_source_unavailable_not_a_crash():
    client = _FakeClient(response=_FakeResponse(200, {"error": "Invalid API key."}))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="bad"), client=client).search_fares(_request())
    assert result.status == "SOURCE_UNAVAILABLE"
    assert "Invalid API key" in result.error_detail


def test_no_flights_at_all_is_empty_result_not_success():
    payload = {"best_flights": [], "other_flights": []}
    client = _FakeClient(response=_FakeResponse(200, payload))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "EMPTY_RESULT"
    assert result.observations == []


def test_non_list_flight_fields_is_malformed_response():
    payload = {"best_flights": "not-a-list", "other_flights": []}
    client = _FakeClient(response=_FakeResponse(200, payload))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "MALFORMED_RESPONSE"


def test_itinerary_missing_required_fields_is_skipped_not_fatal_if_others_succeed():
    payload = {
        "best_flights": [{"flights": [{"garbage": True}], "price": 1000}],
        "other_flights": [_real_shaped_payload()["best_flights"][0]],
    }
    client = _FakeClient(response=_FakeResponse(200, payload))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "SUCCESS"
    assert len(result.observations) == 1


def test_all_itineraries_malformed_is_parse_error_not_fabrication():
    payload = {"best_flights": [{"flights": [{"garbage": True}], "price": 1000}], "other_flights": []}
    client = _FakeClient(response=_FakeResponse(200, payload))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "PARSE_ERROR"
    assert result.observations == []


def test_non_200_status_is_http_error():
    client = _FakeClient(response=_FakeResponse(500, None, text="Internal Server Error"))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "HTTP_ERROR"


def test_timeout_is_reported_as_timeout_not_a_crash():
    client = _FakeClient(raise_exc=httpx.TimeoutException("simulated timeout"))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "TIMEOUT"


def test_network_error_is_http_error_not_a_crash():
    client = _FakeClient(raise_exc=httpx.ConnectError("simulated connection failure"))
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "HTTP_ERROR"


def test_unparseable_json_is_parse_error():
    client = _FakeClient(response=_FakeResponse(200, None))  # .json() raises
    result = SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=client).search_fares(_request())
    assert result.status == "PARSE_ERROR"


def test_source_name():
    assert SerpApiSource(credentials=SerpApiCredentials(api_key="fake"), client=_FakeClient()).name == "SerpApi (Google Flights)"
