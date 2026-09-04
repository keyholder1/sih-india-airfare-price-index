"""Tests for the OpenWeatherMap HTTP client. Uses a fake httpx-like
client injected via the constructor -- no real network calls. Payload
shape matches OpenWeatherMap's documented, long-stable Current Weather
Data contract (see openweather_client.py's module docstring for the
verification caveat: the provided key could not be live-confirmed in
this session due to activation delay)."""

import httpx

from index_engine.openweather_client import OpenWeatherClient, ENV_API_KEY


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("no json configured")
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
    return {
        "coord": {"lon": 77.2090, "lat": 28.6139},
        "weather": [{"id": 500, "main": "Rain", "description": "light rain", "icon": "10d"}],
        "base": "stations",
        "main": {"temp": 28.99, "feels_like": 35.99, "temp_min": 27.0, "temp_max": 30.0, "pressure": 1004, "humidity": 100},
        "visibility": 10000,
        "wind": {"speed": 7.72, "deg": 210},
        "clouds": {"all": 75},
        "dt": 1725444000,
        "sys": {"country": "IN", "sunrise": 1725415800, "sunset": 1725461400},
        "timezone": 19800,
        "id": 1273294,
        "name": "New Delhi",
        "cod": 200,
    }


# --- not configured (no key) ---


def test_missing_api_key_returns_not_configured_without_a_network_call():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = OpenWeatherClient(client=fake, api_key=None)
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "NOT_CONFIGURED"
    assert ENV_API_KEY in result.error_detail
    assert fake.call_count == 0


# --- successful retrieval ---


def test_successful_fetch_returns_success_with_raw_payload():
    client = OpenWeatherClient(client=_FakeClient(response=_FakeResponse(200, _real_shaped_payload())), api_key="fake")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "SUCCESS"
    assert result.data["name"] == "New Delhi"
    assert result.from_cache is False


# --- caching ---


def test_repeated_identical_coords_served_from_cache():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = OpenWeatherClient(client=fake, api_key="fake", cache_ttl_seconds=900)
    client.get_current_weather(28.6139, 77.2090)
    second = client.get_current_weather(28.6139, 77.2090)
    assert second.from_cache is True
    assert fake.call_count == 1


def test_different_coords_are_not_cached_together():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    client = OpenWeatherClient(client=fake, api_key="fake")
    client.get_current_weather(28.6139, 77.2090)
    client.get_current_weather(12.9716, 77.5946)
    assert fake.call_count == 2


# --- error handling ---


def test_401_is_unavailable_not_a_crash():
    client = OpenWeatherClient(client=_FakeClient(response=_FakeResponse(401, {"cod": 401, "message": "Invalid API key."})), api_key="bad")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "UNAVAILABLE"
    assert "401" in result.error_detail


def test_429_is_unavailable():
    client = OpenWeatherClient(client=_FakeClient(response=_FakeResponse(429, None)), api_key="fake")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "UNAVAILABLE"


def test_timeout_is_reported_as_timeout():
    client = OpenWeatherClient(client=_FakeClient(raise_exc=httpx.TimeoutException("simulated")), api_key="fake")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "TIMEOUT"


def test_network_error_is_unavailable():
    client = OpenWeatherClient(client=_FakeClient(raise_exc=httpx.ConnectError("simulated")), api_key="fake")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "UNAVAILABLE"


def test_unparseable_json_is_malformed_response():
    client = OpenWeatherClient(client=_FakeClient(response=_FakeResponse(200, None)), api_key="fake")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "MALFORMED_RESPONSE"


def test_missing_main_field_is_malformed_response():
    client = OpenWeatherClient(client=_FakeClient(response=_FakeResponse(200, {"weather": [{}]})), api_key="fake")
    result = client.get_current_weather(28.6139, 77.2090)
    assert result.status == "MALFORMED_RESPONSE"


# --- request params / key handling ---


def test_request_params_include_units_metric_and_key():
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    OpenWeatherClient(client=fake, api_key="my-secret-key").get_current_weather(28.6139, 77.2090)
    assert fake.last_params["units"] == "metric"
    assert fake.last_params["lat"] == 28.6139
    assert fake.last_params["lon"] == 77.2090
    assert fake.last_params["appid"] == "my-secret-key"


def test_env_var_key_is_read_not_hardcoded(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "env-test-key")
    fake = _FakeClient(response=_FakeResponse(200, _real_shaped_payload()))
    OpenWeatherClient(client=fake).get_current_weather(28.6139, 77.2090)
    assert fake.last_params["appid"] == "env-test-key"


def test_key_never_appears_in_returned_data():
    secret = "SUPER-SECRET-OWM-KEY"
    client = OpenWeatherClient(client=_FakeClient(response=_FakeResponse(200, _real_shaped_payload())), api_key=secret)
    result = client.get_current_weather(28.6139, 77.2090)
    assert secret not in str(result.data)
