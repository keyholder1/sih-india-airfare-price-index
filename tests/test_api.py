from fastapi.testclient import TestClient

from api.main import app
from conftest import make_observation

client = TestClient(app)


def _rows():
    base = [make_observation(flight_date="2026-01-15", booking_date="2026-01-01", total_fare=5000.0 + i) for i in range(5)]
    current = [make_observation(flight_date="2026-08-15", booking_date="2026-08-01", total_fare=5500.0 + i) for i in range(5)]
    return base + current


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_calculate_endpoint_returns_expected_index():
    payload = {
        "base_period": "2026-01",
        "current_period": "2026-08",
        "observations": _rows(),
    }
    response = client.post("/index/calculate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert abs(body["national_index"] - 110.0) < 1.0
    assert body["routes_covered"] == 1


def test_calculate_endpoint_rejects_insufficient_data():
    payload = {
        "base_period": "2026-01",
        "current_period": "2026-08",
        "observations": [dict(make_observation(total_fare=-1))],
    }
    response = client.post("/index/calculate", json=payload)
    assert response.status_code == 422


def test_timeseries_endpoint_returns_one_result_per_period():
    payload = {
        "base_period": "2026-01",
        "periods": ["2026-01", "2026-08"],
        "observations": _rows(),
    }
    response = client.post("/index/timeseries", json=payload)
    assert response.status_code == 200
    assert len(response.json()) == 2
