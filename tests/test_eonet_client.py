"""Tests for the EONET HTTP client. Uses a fake httpx-like client
injected via the constructor -- no real network calls. Payload shapes
are trimmed-down versions of REAL responses captured live from
https://eonet.gsfc.nasa.gov/api/v3/events during this project's recon
(2026-09-04)."""

import httpx
import pytest

from index_engine.eonet_client import EonetClient, ENV_API_KEY


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("no json configured on fake response")
        return self._json_data


class _FakeClient:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.last_params = None
        self.call_count = 0

    def get(self, url, params=None):
        self.call_count += 1
        self.last_params = params
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response

    def close(self):
        pass


def _real_shaped_payload():
    # Trimmed from a real captured response (Nevada wildfire, Point
    # geometry -- verified [lon, lat] ordering) plus one real India
    # wildfire, both verified live 2026-09-04.
    return {
        "title": "EONET Events",
        "events": [
            {
                "id": "EONET_23868",
                "title": "Emergency Stabilization BAER McConnell, Humboldt, Nevada",
                "categories": [{"id": "wildfires", "title": "Wildfires"}],
                "sources": [{"id": "IRWIN", "url": "https://irwin.doi.gov/observer/incidents/2026-NVWID-020663"}],
                "closed": None,
                "geometry": [
                    {"date": "2026-09-03T13:03:00Z", "type": "Point", "coordinates": [-117.74215, 41.517567], "magnitudeValue": 500.0, "magnitudeUnit": "acres"}
                ],
            },
            {
                "id": "EONET_20378",
                "title": "Wildfire in India 1028830",
                "categories": [{"id": "wildfires", "title": "Wildfires"}],
                "sources": [],
                "closed": "2026-06-01T00:00:00Z",
                "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_20378",
                "geometry": [{"date": "2026-05-31T19:00:00Z", "type": "Point", "coordinates": [82.67436957186071, 21.84448418414697]}],
            },
        ],
    }


# --- successful retrieval ---


def test_successful_fetch_returns_success_with_events():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, _real_shaped_payload())))
    result = client.get_events(category="wildfires", bbox="68,6,98,37", days=45)
    assert result.status == "SUCCESS"
    assert len(result.events) == 2
    assert result.from_cache is False


def test_empty_events_list_is_still_success():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, {"title": "EONET Events", "events": []})))
    result = client.get_events()
    assert result.status == "SUCCESS"
    assert result.events == []


# --- caching ---


def test_repeated_identical_call_is_served_from_cache():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = EonetClient(client=fake, cache_ttl_seconds=900)
    first = client.get_events(category="wildfires", days=45)
    second = client.get_events(category="wildfires", days=45)
    assert first.from_cache is False
    assert second.from_cache is True
    assert fake.call_count == 1  # only one real request made


def test_different_params_are_not_cached_together():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = EonetClient(client=fake)
    client.get_events(category="wildfires")
    client.get_events(category="floods")
    assert fake.call_count == 2


def test_expired_cache_entry_triggers_a_real_refetch():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = EonetClient(client=fake, cache_ttl_seconds=-1)  # already expired
    client.get_events(category="wildfires")
    client.get_events(category="wildfires")
    assert fake.call_count == 2


# --- error handling ---


def test_timeout_is_reported_as_timeout_not_a_crash():
    client = EonetClient(client=_FakeClient(raise_exc=httpx.TimeoutException("simulated timeout")))
    result = client.get_events()
    assert result.status == "TIMEOUT"
    assert result.events == []


def test_network_error_is_unavailable_not_a_crash():
    client = EonetClient(client=_FakeClient(raise_exc=httpx.ConnectError("simulated connection failure")))
    result = client.get_events()
    assert result.status == "UNAVAILABLE"


def test_rate_limit_429_is_unavailable():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(429, None)))
    result = client.get_events()
    assert result.status == "UNAVAILABLE"
    assert "429" in result.error_detail


def test_non_200_status_is_unavailable():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(500, None)))
    result = client.get_events()
    assert result.status == "UNAVAILABLE"


def test_unparseable_json_is_malformed_response():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, None)))  # .json() raises
    result = client.get_events()
    assert result.status == "MALFORMED_RESPONSE"


def test_non_dict_payload_is_malformed_response():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, ["not", "a", "dict"])))
    result = client.get_events()
    assert result.status == "MALFORMED_RESPONSE"


def test_missing_events_field_is_malformed_response():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, {"title": "EONET Events"})))
    result = client.get_events()
    assert result.status == "MALFORMED_RESPONSE"


def test_events_not_a_list_is_malformed_response():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, {"events": "not-a-list"})))
    result = client.get_events()
    assert result.status == "MALFORMED_RESPONSE"


# --- request params / no-key-required behaviour ---


def test_no_api_key_omits_api_key_param():
    fake = _FakeClient(response=_FakeResponse(200, {"events": []}))
    EonetClient(client=fake, api_key=None).get_events()
    assert "api_key" not in fake.last_params


def test_configured_api_key_is_included_but_never_returned():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = EonetClient(client=fake, api_key="super-secret-test-key")
    result = client.get_events()
    assert fake.last_params["api_key"] == "super-secret-test-key"
    # The key must never leak into the returned events or error_detail.
    assert "super-secret-test-key" not in str(result.events)
    assert result.error_detail is None or "super-secret-test-key" not in result.error_detail


def test_env_var_key_is_read_and_not_hardcoded(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "env-test-key")
    fake = _FakeClient(response=_FakeResponse(200, {"events": []}))
    EonetClient(client=fake).get_events()
    assert fake.last_params["api_key"] == "env-test-key"


def test_multi_category_comma_list_passed_through():
    fake = _FakeClient(response=_FakeResponse(200, {"events": []}))
    EonetClient(client=fake).get_events(category="severeStorms,wildfires,volcanoes")
    assert fake.last_params["category"] == "severeStorms,wildfires,volcanoes"


def test_bbox_passed_through_unmodified():
    fake = _FakeClient(response=_FakeResponse(200, {"events": []}))
    EonetClient(client=fake).get_events(bbox="68,6,98,37")
    assert fake.last_params["bbox"] == "68,6,98,37"
