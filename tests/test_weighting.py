import pandas as pd

from index_engine.weighting import generate_synthetic_weights, normalize_weights, weights_for_period


def test_normalize_weights_sums_to_one():
    weights = pd.DataFrame(
        {"origin": ["BLR", "DEL"], "destination": ["DEL", "BOM"], "weight": [3.0, 1.0]}
    )
    normalized = normalize_weights(weights)
    assert abs(normalized["weight_normalized"].sum() - 1.0) < 1e-9
    assert abs(normalized.loc[0, "weight_normalized"] - 0.75) < 1e-9


def test_synthetic_weights_are_clearly_labelled():
    weights = generate_synthetic_weights(["BLR-DEL", "DEL-BOM"])
    assert (weights["source"] == "SYNTHETIC_DEMO_ONLY").all()


def test_weights_for_period_respects_effective_dates():
    weights = pd.DataFrame(
        {
            "origin": ["BLR", "BLR"],
            "destination": ["DEL", "DEL"],
            "weight": [1.0, 2.0],
            "effective_from": [None, "2026-06-01"],
            "effective_to": ["2026-05-31", None],
        }
    )
    early = weights_for_period(weights, "2026-02")
    late = weights_for_period(weights, "2026-08")
    assert early["weight"].tolist() == [1.0]
    assert late["weight"].tolist() == [2.0]
