"""Tests for weather_context.py's orchestration layer -- fetching real
conditions at a route's two airports independently, with independent
failure isolation for each side, and no key leakage."""

import httpx

from index_engine.openweather_client import OpenWeatherClient
from index_engine.weather_context import WeatherContextService


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class _FakeClient:
    """Returns a different fixture depending on the requested lat/lon --
    simulates origin succeeding while destination fails, and vice versa."""

    def __init__(self, responses_by_latlon=None, default=None, raise_exc=None):
        self._responses = responses_by_latlon or {}
        self._default = default
        self._raise_exc = raise_exc

    def get(self, url, params=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        key = (round(params["lat"], 4), round(params["lon"], 4))
        return self._responses.get(key, self._default)

    def close(self):
        pass


def _payload(name="City", temp=28.0):
    return {
        "coord": {"lon": 0, "lat": 0},
        "weather": [{"main": "Clear", "description": "clear sky"}],
        "main": {"temp": temp, "feels_like": temp + 2, "humidity": 50},
        "wind": {"speed": 2.5},
        "visibility": 10000,
        "dt": 1725444000,
        "name": name,
    }


def test_both_airports_succeed_status_ok():
    fake = _FakeClient(default=_FakeResponse(200, _payload("Bengaluru", 29.0)))
    service = WeatherContextService(client=OpenWeatherClient(client=fake, api_key="fake"))
    result = service.get_route_weather("BLR", "DEL")
    assert result.status == "OK"
    assert result.origin is not None
    assert result.destination is not None
    assert result.error_detail is None


def test_unknown_iata_code_is_isolated_to_that_side():
    fake = _FakeClient(default=_FakeResponse(200, _payload("Bengaluru", 29.0)))
    service = WeatherContextService(client=OpenWeatherClient(client=fake, api_key="fake"))
    result = service.get_route_weather("BLR", "ZZZ")  # ZZZ has no known coordinates
    assert result.status == "PARTIAL"
    assert result.origin is not None
    assert result.destination is None
    assert "ZZZ" in result.error_detail


def test_both_unknown_is_unavailable():
    service = WeatherContextService(client=OpenWeatherClient(client=_FakeClient(), api_key="fake"))
    result = service.get_route_weather("ZZZ", "YYY")
    assert result.status == "UNAVAILABLE"
    assert result.origin is None
    assert result.destination is None


def test_network_failure_for_both_sides_is_unavailable_not_a_crash():
    fake = _FakeClient(raise_exc=httpx.ConnectError("simulated outage"))
    service = WeatherContextService(client=OpenWeatherClient(client=fake, api_key="fake"))
    result = service.get_route_weather("BLR", "DEL")
    assert result.status == "UNAVAILABLE"


def test_not_configured_client_is_isolated_not_a_crash():
    service = WeatherContextService(client=OpenWeatherClient(client=_FakeClient(), api_key=None))
    result = service.get_route_weather("BLR", "DEL")
    assert result.status == "UNAVAILABLE"
    assert result.origin is None
    assert result.destination is None


def test_get_route_weather_never_raises_even_if_client_raises(monkeypatch):
    client = OpenWeatherClient(client=_FakeClient(default=_FakeResponse(200, _payload())), api_key="fake")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated internal bug")

    monkeypatch.setattr(client, "get_current_weather", _boom)
    service = WeatherContextService(client=client)
    result = service.get_route_weather("BLR", "DEL")  # must not raise
    assert result.status == "UNAVAILABLE"


def test_api_key_never_appears_in_route_weather_result():
    secret = "SUPER-SECRET-OWM-KEY"
    fake = _FakeClient(default=_FakeResponse(200, _payload("Bengaluru", 29.0)))
    service = WeatherContextService(client=OpenWeatherClient(client=fake, api_key=secret))
    result = service.get_route_weather("BLR", "DEL")
    assert secret not in str(result.to_dict())
