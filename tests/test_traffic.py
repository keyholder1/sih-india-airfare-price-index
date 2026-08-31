from pathlib import Path

import pandas as pd

from index_engine.city_mapping import city_to_iata, iata_to_city
from index_engine.traffic import (
    REASON_DUPLICATE,
    REASON_INVALID_PASSENGERS,
    REASON_SAME_CITY,
    aggregate_period,
    build_dgca_weights,
    covered_subset,
    national_weights,
    rolling_window,
    to_directional,
    to_engine_weights,
    validate_traffic,
)

REAL_DGCA_CSV = Path(__file__).parent.parent / "data" / "traffic" / "dgca_domestic_city_pairs.csv"


def _traffic_row(**overrides):
    row = {"Year": 2026, "Month": 6, "City1": "DELHI", "City2": "MUMBAI", "PaxToCity2": 100, "PaxFromCity2": 90}
    row.update(overrides)
    return row


def test_city_mapping_round_trip():
    assert iata_to_city("DEL") == "DELHI"
    assert city_to_iata("DELHI") == "DEL"


def test_national_weight_manual_calculation():
    """Route A=600, B=300, C=100 passengers -> weights 0.60, 0.30, 0.10 exactly."""
    route_passengers = pd.DataFrame(
        {
            "origin": ["A1", "B1", "C1"],
            "destination": ["A2", "B2", "C2"],
            "passengers": [600, 300, 100],
        }
    )
    result = national_weights(route_passengers)
    weights = dict(zip(result["origin"], result["national_weight"]))
    assert abs(weights["A1"] - 0.60) < 1e-9
    assert abs(weights["B1"] - 0.30) < 1e-9
    assert abs(weights["C1"] - 0.10) < 1e-9


def test_directional_routes_stay_directional():
    valid, _ = validate_traffic(pd.DataFrame([_traffic_row(PaxToCity2=100, PaxFromCity2=90)]))
    long_df = to_directional(valid, source="DGCA")
    forward = long_df[(long_df.origin == "DELHI") & (long_df.destination == "MUMBAI")]
    backward = long_df[(long_df.origin == "MUMBAI") & (long_df.destination == "DELHI")]
    assert forward["passengers"].iloc[0] == 100
    assert backward["passengers"].iloc[0] == 90


def test_same_origin_destination_rejected():
    _, rejected = validate_traffic(pd.DataFrame([_traffic_row(City1="DELHI", City2="DELHI")]))
    assert rejected["rejection_reason"].iloc[0] == REASON_SAME_CITY


def test_negative_passenger_count_rejected():
    _, rejected = validate_traffic(pd.DataFrame([_traffic_row(PaxToCity2=-5)]))
    assert rejected["rejection_reason"].iloc[0] == REASON_INVALID_PASSENGERS


def test_duplicate_traffic_record_rejected():
    rows = [_traffic_row(), _traffic_row()]
    valid, rejected = validate_traffic(pd.DataFrame(rows))
    assert len(valid) == 1
    assert rejected["rejection_reason"].iloc[0] == REASON_DUPLICATE


def test_route_with_no_traffic_in_window_is_absent_not_zero():
    long_df = to_directional(validate_traffic(pd.DataFrame([_traffic_row(Year=2025, Month=1)]))[0], source="DGCA")
    aggregated = aggregate_period(long_df, "2026-01", "2026-06")  # window that excludes the only record
    assert aggregated.empty  # absent, not a zero-passenger row


def test_rolling_window_is_twelve_months_inclusive_and_not_hardcoded():
    start, end = rolling_window("2026-05", months=12)
    assert end == "2026-05"
    assert start == "2025-06"


def test_covered_subset_renormalizes_and_reports_coverage():
    national = pd.DataFrame(
        {
            "origin": ["X", "Y", "Z"],
            "destination": ["X2", "Y2", "Z2"],
            "passengers": [700, 200, 100],
            "national_weight": [0.7, 0.2, 0.1],
        }
    )
    covered = covered_subset(national, [("X", "X2"), ("Y", "Y2")])  # Z excluded (not airfare-covered)
    assert abs(covered["covered_normalized_weight"].sum() - 1.0) < 1e-9
    x_weight = covered.loc[covered.origin == "X", "covered_normalized_weight"].iloc[0]
    assert abs(x_weight - (0.7 / 0.9)) < 1e-9


def test_to_engine_weights_maps_to_iata_and_is_engine_compatible():
    covered = pd.DataFrame(
        {
            "origin": ["DELHI"],
            "destination": ["MUMBAI"],
            "passengers": [1000],
            "national_weight": [0.05],
            "covered_normalized_weight": [1.0],
        }
    )
    engine_weights = to_engine_weights(covered, "2025-06", "2026-05")
    assert engine_weights["origin"].iloc[0] == "DEL"
    assert engine_weights["destination"].iloc[0] == "BOM"
    assert engine_weights["source"].iloc[0] == "DGCA_DERIVED"
    assert engine_weights["effective_from"].iloc[0] is None  # open-ended, not tied to the measurement window
    assert engine_weights["weight_period_start"].iloc[0] == "2025-06"
    assert engine_weights["weight_period_end"].iloc[0] == "2026-05"


def test_build_dgca_weights_against_real_committed_dataset():
    """Integration test against the actual committed DGCA file (real data,
    not synthetic) for the 6-city route universe used by the fare demo."""
    routes = [
        ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
        ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
        ("CCU", "DEL"), ("BLR", "BOM"),
    ]
    engine_weights, diagnostics = build_dgca_weights(str(REAL_DGCA_CSV), routes)

    assert len(engine_weights) == len(routes)
    assert abs(engine_weights["weight"].sum() - 1.0) < 1e-6
    assert (engine_weights["source"] == "DGCA_DERIVED").all()
    assert 0.0 < diagnostics["traffic_weight_coverage"] < 1.0
    assert diagnostics["total_routes_in_window"] > len(routes)  # real network is much bigger than our 10 routes
    assert diagnostics["weight_period_end"] < "2026-08"  # real data lags behind the fictional "today"
