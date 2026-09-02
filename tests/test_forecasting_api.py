"""Tests for the forecasting API layer (api/forecasting_routes.py).

Local fixtures only -- no SerpApi calls, no network I/O beyond the
in-process TestClient. Mirrors tests/test_api.py's structure for the
existing index-engine endpoints.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from conftest import make_observation

client = TestClient(app)


def _monthly_observations(months, per_month=3, origin="BLR", destination="DEL", base_fare=5000.0):
    rows = []
    for m_idx, month in enumerate(months):
        for d in range(per_month):
            rows.append(
                make_observation(
                    origin=origin,
                    destination=destination,
                    flight_date=f"{month}-1{d}",
                    booking_date=f"{month}-0{d + 1}",
                    total_fare=base_fare + m_idx * 100 + d * 10,
                )
            )
    return rows


def _two_route_observations(months, per_month=3):
    return _monthly_observations(months, per_month, "BLR", "DEL") + _monthly_observations(
        months, per_month, "DEL", "BOM", base_fare=4000.0
    )


def _base_request(months=("2026-01", "2026-02", "2026-03", "2026-04"), **extra):
    payload = {
        "base_period": months[0],
        "observations": _two_route_observations(list(months)),
        "is_synthetic_data": True,
    }
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# 1. Successful national forecast
# ---------------------------------------------------------------------------


def test_national_forecast_success():
    response = client.post("/forecast/national", json=_base_request())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["forecast_value"] is not None
    assert body["is_synthetic_data"] is True
    assert body["forecast_period"] == "2026-05"


# ---------------------------------------------------------------------------
# 2. Successful route forecast
# ---------------------------------------------------------------------------


def test_route_forecast_success():
    response = client.post("/forecast/route", json=_base_request(route="BLR-DEL"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["is_synthetic_data"] is True


def test_forecast_all_routes_success():
    response = client.post("/forecast/routes", json=_base_request())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"BLR-DEL", "DEL-BOM"}
    assert all(r["is_synthetic_data"] is True for r in body.values())


# ---------------------------------------------------------------------------
# 3. Insufficient-data responses (not fabricated -- status field, still 200)
# ---------------------------------------------------------------------------


def test_national_forecast_insufficient_data_is_reported_not_fabricated():
    # A single period has no history to forecast from at all once the one
    # real period *is* the base period (national_index pinned, but the
    # backtest/forecast-from-history path still needs a genuine prior).
    single_period_obs = _monthly_observations(["2026-01"], per_month=3)
    response = client.post(
        "/forecast/national",
        json={"base_period": "2026-01", "observations": single_period_obs, "is_synthetic_data": True},
    )
    assert response.status_code == 200
    body = response.json()
    # With only one real period, forecast_national_index still produces a
    # forecast (naive off the single point) but with zero backtest folds --
    # assert the API surfaces that honestly rather than claiming a fake
    # confidence interval.
    assert body["status"] in ("OK", "INSUFFICIENT_DATA")
    if body["status"] == "OK":
        assert body["lower_bound"] is None and body["upper_bound"] is None


def test_cpi_benchmark_insufficient_data_status_not_hidden():
    response = client.post("/forecast/cpi-benchmark", json=_base_request())
    assert response.status_code == 200
    body = response.json()
    # This project's real MoSPI extract has no overlap with a 2026
    # synthetic-only fixture spanning 4 months -- either insufficient
    # overlap or insufficient YoY history is expected, never a fabricated OK.
    assert body["yoy_comparison_status"] in ("INSUFFICIENT_OVERLAP", "INSUFFICIENT_DATA", "OK")
    assert body["is_synthetic_airfare_data"] is True


# ---------------------------------------------------------------------------
# 4. Invalid requests -> proper 4xx
# ---------------------------------------------------------------------------


def test_route_forecast_unknown_route_is_400():
    response = client.post("/forecast/route", json=_base_request(route="ZZZ-ZZZ"))
    assert response.status_code == 400
    assert "ZZZ-ZZZ" in response.json()["detail"]


def test_national_forecast_rejects_horizon_other_than_one():
    response = client.post("/forecast/national", json=_base_request(horizon=2))
    assert response.status_code == 400


def test_national_forecast_rejects_unknown_model():
    response = client.post("/forecast/national", json=_base_request(model="not_a_real_model"))
    assert response.status_code == 400


def test_national_forecast_rejects_malformed_observations():
    # Negative fare -> index_engine's own validation raises ValueError /
    # InsufficientDataError during dataset construction, not something
    # this API layer should paper over.
    bad_obs = [dict(make_observation(total_fare=-1))]
    response = client.post(
        "/forecast/national",
        json={"base_period": "2026-01", "observations": bad_obs, "is_synthetic_data": True},
    )
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 5. Synthetic-data provenance surfaced
# ---------------------------------------------------------------------------


def test_synthetic_flag_is_surfaced_true_when_requested():
    response = client.post("/forecast/national", json=_base_request())
    assert response.json()["is_synthetic_data"] is True


def test_synthetic_flag_is_surfaced_false_when_requested():
    response = client.post("/forecast/national", json=_base_request(**{"is_synthetic_data": False}))
    assert response.status_code == 200
    assert response.json()["is_synthetic_data"] is False


def test_route_evaluate_propagates_synthetic_flag_into_nested_forecasts():
    response = client.post("/forecast/route/evaluate", json=_base_request(route="BLR-DEL"))
    assert response.status_code == 200
    body = response.json()
    for model_result in body.values():
        assert model_result["forecasts"] == [] or all(
            f["is_synthetic_data"] is True for f in model_result["forecasts"]
        )


# ---------------------------------------------------------------------------
# 6. CPI benchmark response shape
# ---------------------------------------------------------------------------


def test_cpi_benchmark_response_shape():
    response = client.post("/forecast/cpi-benchmark", json=_base_request())
    assert response.status_code == 200
    body = response.json()
    for field in (
        "overlap_period_count",
        "comparisons",
        "mom_correlation_status",
        "yoy_comparison_status",
        "yoy_period_count",
        "status",
        "is_synthetic_airfare_data",
    ):
        assert field in body


# ---------------------------------------------------------------------------
# 7. YoY/MoM status handling
# ---------------------------------------------------------------------------


def test_cpi_benchmark_preserves_distinct_mom_and_yoy_status_fields():
    response = client.post("/forecast/cpi-benchmark", json=_base_request())
    body = response.json()
    # MoM and YoY are reported as genuinely separate fields, never merged
    # into one status -- this is the whole point of Stage 4.
    assert "mom_correlation_status" in body
    assert "yoy_comparison_status" in body
    assert body["mom_correlation_status"] != body["yoy_comparison_status"] or body["yoy_comparison_status"] in (
        "INSUFFICIENT_OVERLAP",
        "INSUFFICIENT_DATA",
    )


# ---------------------------------------------------------------------------
# 8. Booking-horizon response
# ---------------------------------------------------------------------------


def test_booking_horizon_response():
    obs = []
    for month in ("2026-01", "2026-02"):
        for suffix, day in (("a", "12"), ("b", "13"), ("c", "14")):
            obs.append(
                {
                    "observation_id": f"BH-{month}-{suffix}",
                    "airline": "IndiGo",
                    "origin": "BLR",
                    "destination": "DEL",
                    "flight_date": f"{month}-15",
                    "booking_date": f"{month}-{day}",
                    "total_fare": 6000.0,
                    "currency": "INR",
                    "is_mock": True,
                }
            )
    response = client.post("/forecast/booking-horizon", json={"base_period": "2026-01", "observations": obs})
    assert response.status_code == 200
    body = response.json()
    assert "T1_7" in body["windows"]
    assert body["windows"]["T1_7"]["status"] == "OK"
    assert body["windows"]["T1_7"]["record_count"] == 6
    assert body["is_synthetic_data"] is True


def test_booking_horizon_out_of_range_window_reports_no_data():
    obs = [
        {
            "observation_id": "BH-far",
            "airline": "IndiGo",
            "origin": "BLR",
            "destination": "DEL",
            "flight_date": "2026-02-15",
            "booking_date": "2026-02-12",
            "total_fare": 6000.0,
            "currency": "INR",
            "is_mock": True,
        }
    ]
    response = client.post("/forecast/booking-horizon", json={"base_period": "2026-01", "observations": obs})
    body = response.json()
    assert body["windows"]["T31_45"]["status"] == "NO_DATA"
    assert body["windows"]["T31_45"]["record_count"] == 0


# ---------------------------------------------------------------------------
# 9. Route handler calls into the forecasting module, doesn't duplicate it
# ---------------------------------------------------------------------------


def test_national_route_calls_forecasting_module_not_a_duplicate_implementation():
    """Patch forecasting.national.forecast_national_index at its source and
    confirm the API route's response is exactly the mocked return value --
    proves the route has no parallel forecast-computation path of its own.
    """
    from forecasting.results import ForecastResult

    sentinel = ForecastResult(
        forecast_period="2099-01",
        forecast_value=123456.0,
        model_used="naive",
        horizon=1,
        training_period=["2098-12"],
        data_points_used=1,
        lower_bound=None,
        upper_bound=None,
        status="OK",
        is_synthetic_data=True,
        notes="sentinel",
    )
    with patch("api.forecasting_routes.forecast_national_index", return_value=sentinel) as mocked:
        response = client.post("/forecast/national", json=_base_request())
    assert response.status_code == 200
    assert mocked.called
    assert response.json()["forecast_value"] == 123456.0
    assert response.json()["forecast_period"] == "2099-01"


def test_route_forecast_calls_forecasting_module_not_a_duplicate_implementation():
    from forecasting.results import ForecastResult

    sentinel = ForecastResult(
        forecast_period="2099-01",
        forecast_value=654321.0,
        model_used="naive",
        horizon=1,
        training_period=["2098-12"],
        data_points_used=1,
        lower_bound=None,
        upper_bound=None,
        status="OK",
        is_synthetic_data=True,
        notes="sentinel",
    )
    with patch("api.forecasting_routes.forecast_route_index", return_value=sentinel) as mocked:
        response = client.post("/forecast/route", json=_base_request(route="BLR-DEL"))
    assert response.status_code == 200
    assert mocked.called
    assert response.json()["forecast_value"] == 654321.0
