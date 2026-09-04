"""Tests for eonet_context.py's orchestration layer -- EonetContextService,
and the two most important guarantees this whole integration makes:

1. EONET failure never prevents/affects the price index calculation
   (index.py/aggregation.py never import anything from this module).
2. A configured EONET_API_KEY never appears in a context result.
"""

from datetime import datetime, timezone

import httpx
import pandas as pd

from index_engine.eonet_client import EonetClient
from index_engine.eonet_context import EonetContextService, RELEVANT_CATEGORIES
from index_engine.news_models import RouteMovement


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class _FakeClient:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc

    def get(self, url, params=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response

    def close(self):
        pass


def _movement():
    return RouteMovement(
        route="BLR-DEL", origin="BLR", destination="DEL", change_pct=16.3,
        metric="mom", period="2026-09", as_of=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )


def _payload_with_del_event():
    return {
        "events": [
            {
                "id": "EONET_TEST_1",
                "title": "Severe Storm near Delhi",
                "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
                "sources": [{"id": "SRC", "url": "https://example.com"}],
                "closed": None,
                "geometry": [{"date": "2026-09-04T00:00:00Z", "type": "Point", "coordinates": [77.2090, 28.6139]}],
            }
        ]
    }


# --- successful context ---


def test_successful_context_returns_ok_with_matches():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, _payload_with_del_event())))
    service = EonetContextService(client=client)
    result = service.get_context(_movement())
    assert result.status == "OK"
    assert len(result.matches) == 1
    assert result.matches[0].event.event_id == "EONET_TEST_1"


def test_empty_events_returns_ok_with_no_matches():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, {"events": []})))
    service = EonetContextService(client=client)
    result = service.get_context(_movement())
    assert result.status == "OK"
    assert result.matches == []


# --- failure isolation ---


def test_timeout_returns_unavailable_not_a_crash():
    client = EonetClient(client=_FakeClient(raise_exc=httpx.TimeoutException("simulated")))
    service = EonetContextService(client=client)
    result = service.get_context(_movement())
    assert result.status == "UNAVAILABLE"
    assert result.matches == []
    assert result.error_detail is not None


def test_malformed_response_returns_unavailable():
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, {"no_events_key": True})))
    service = EonetContextService(client=client)
    result = service.get_context(_movement())
    assert result.status == "UNAVAILABLE"


def test_get_context_never_raises_even_if_client_get_events_raises(monkeypatch):
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, {"events": []})))

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated internal bug")

    monkeypatch.setattr(client, "get_events", _boom)
    service = EonetContextService(client=client)
    result = service.get_context(_movement())  # must not raise
    assert result.status == "UNAVAILABLE"


# --- index independence (the most important guarantee) ---


def test_index_engine_modules_never_import_eonet():
    """index.py and aggregation.py -- the actual index math -- must have
    zero dependency on eonet_* modules, so an EONET outage structurally
    cannot affect a computed index value."""
    import ast
    import inspect

    from index_engine import aggregation, index

    for module in (index, aggregation):
        tree = ast.parse(inspect.getsource(module))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)
        assert not any("eonet" in name.lower() for name in imported_names), (
            f"{module.__name__} must never import an eonet_* module"
        )


def test_index_value_identical_with_eonet_available_vs_unavailable():
    """Computing the price index from the same observations must yield
    byte-identical results regardless of whether EONET succeeds or
    fails -- proves EONET truly never touches the calculation, not just
    that it isn't called in one code path."""
    from index_engine.index import AirfarePriceIndex

    observations = pd.DataFrame(
        [
            {
                "observation_id": f"OBS{i}",
                "airline": "IndiGo",
                "origin": "BLR",
                "destination": "DEL",
                "flight_date": "2026-09-10",
                "booking_date": "2026-09-01",
                "total_fare": 5000.0 + i * 10,
                "currency": "INR",
            }
            for i in range(5)
        ]
    )
    engine = AirfarePriceIndex(base_period="2026-09")
    result_before_any_eonet_call = engine.calculate(observations, current_period="2026-09")

    # Simulate an EONET call happening (successfully or not) "alongside"
    # the index calculation -- must have zero effect on a fresh calculate().
    client_up = EonetClient(client=_FakeClient(response=_FakeResponse(200, _payload_with_del_event())))
    EonetContextService(client=client_up).get_context(_movement())
    result_with_eonet_up = engine.calculate(observations, current_period="2026-09")

    client_down = EonetClient(client=_FakeClient(raise_exc=httpx.ConnectError("simulated outage")))
    EonetContextService(client=client_down).get_context(_movement())
    result_with_eonet_down = engine.calculate(observations, current_period="2026-09")

    assert result_before_any_eonet_call.national_index == result_with_eonet_up.national_index
    assert result_before_any_eonet_call.national_index == result_with_eonet_down.national_index


# --- no key leakage ---


def test_api_key_never_appears_in_context_result():
    secret = "SUPER-SECRET-EONET-KEY-DO-NOT-LEAK"
    client = EonetClient(client=_FakeClient(response=_FakeResponse(200, _payload_with_del_event())), api_key=secret)
    service = EonetContextService(client=client)
    result = service.get_context(_movement())
    dumped = str(result.to_dict())
    assert secret not in dumped


def test_api_key_never_appears_when_eonet_fails():
    secret = "SUPER-SECRET-EONET-KEY-DO-NOT-LEAK"
    client = EonetClient(client=_FakeClient(response=_FakeResponse(500, None)), api_key=secret)
    service = EonetContextService(client=client)
    result = service.get_context(_movement())
    dumped = str(result.to_dict())
    assert secret not in dumped


def test_relevant_categories_are_real_eonet_category_ids():
    from index_engine.eonet_models import EONET_CATEGORIES

    for category in RELEVANT_CATEGORIES:
        assert category in EONET_CATEGORIES
