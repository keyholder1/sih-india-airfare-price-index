"""Loads whatever real fare data this checkout actually has on disk, with
an honestly-labeled synthetic fallback when it doesn't.

This is the seam between the API's Protocol adapters (real_adapters.py)
and the project's actual data sources: the scraper's persisted
validated/raw fare files (see scraper.storage's module docstring for the
data/ layout) and, when none exist yet, a small deterministic demo
dataset. Nothing here does statistics -- it only loads and labels data;
index_engine/data_quality do the actual computation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from index_engine import traffic as traffic_mod
from index_engine import weighting as weighting_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
DGCA_TRAFFIC_CSV = str(REPO_ROOT / "data" / "traffic" / "dgca_domestic_city_pairs.csv")

#: Demo routes used only when no persisted scraper output exists at all
#: (e.g. a fresh checkout before any scrape has run). Matches the routes
#: already covered by the real scraper's mock run so behaviour is
#: consistent whether or not that run's output is present.
_FALLBACK_ROUTES = [
    ("BLR", "DEL"),
    ("DEL", "BLR"),
    ("DEL", "BOM"),
    ("BOM", "DEL"),
    ("HYD", "DEL"),
]


def _read_jsonl_dir(dir_path: Path) -> List[Dict[str, Any]]:
    if not dir_path.is_dir():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(dir_path.glob("*.jsonl")):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


#: Provenance classification for a batch of observations. A batch is
#: REAL only when *every* observation is genuinely scraped; MIXED when
#: some but not all are -- a mixed batch must never be silently promoted
#: to REAL just because at least one real observation is present.
PROVENANCE_REAL = "REAL"
PROVENANCE_SYNTHETIC = "SYNTHETIC"
PROVENANCE_MIXED = "MIXED"
PROVENANCE_UNAVAILABLE = "UNAVAILABLE"


def classify_provenance(observations: List[Dict[str, Any]]) -> str:
    """REAL only when every observation is non-mock, SYNTHETIC only when
    every observation is mock, MIXED when both appear, UNAVAILABLE when
    there are no observations at all -- see docs/scraper.md "Raw vs
    validated storage"."""
    if not observations:
        return PROVENANCE_UNAVAILABLE
    mock_flags = [bool(obs.get("is_mock", True)) for obs in observations]
    if all(mock_flags):
        return PROVENANCE_SYNTHETIC
    if not any(mock_flags):
        return PROVENANCE_REAL
    return PROVENANCE_MIXED


def _generate_fallback_observations(n_months: int = 8) -> List[Dict[str, Any]]:
    """Deterministic, clearly-labeled synthetic dataset for when no
    scraper output exists on disk at all. Spans ``n_months`` starting
    2026-01, matching the convention used throughout examples/ and docs/.
    """
    observations: List[Dict[str, Any]] = []
    base_fare_by_route = {route: 4000.0 + 300.0 * i for i, route in enumerate(_FALLBACK_ROUTES)}
    obs_id = 0
    for month in range(1, n_months + 1):
        period = f"2026-{month:02d}"
        for origin, destination in _FALLBACK_ROUTES:
            route = f"{origin}-{destination}"
            base_fare = base_fare_by_route[route]
            # Small deterministic month-over-month drift so MoM/YoY are
            # non-trivial without being random (tests must be reproducible).
            fare = round(base_fare * (1.0 + 0.01 * month), 2)
            for day in (5, 15, 25):
                obs_id += 1
                observations.append(
                    {
                        "observation_id": f"FALLBACK-{obs_id:05d}",
                        "airline": "UNKNOWN",
                        "origin": origin,
                        "destination": destination,
                        "flight_date": f"{period}-{day:02d}",
                        "booking_date": f"{period}-01",
                        "total_fare": fare,
                        "currency": "INR",
                        "source": "internal_demo_fallback",
                        "is_mock": True,
                    }
                )
    return observations


def load_validated_observations() -> Tuple[List[Dict[str, Any]], str]:
    """Returns (observations, provenance) -- see ``classify_provenance``
    for the PROVENANCE_* values. Falls back to a synthetic demo dataset
    (PROVENANCE_SYNTHETIC) when nothing has been scraped and validated
    yet."""
    observations = _read_jsonl_dir(REPO_ROOT / "data" / "validated" / "fares")
    if not observations:
        return _generate_fallback_observations(), PROVENANCE_SYNTHETIC
    return observations, classify_provenance(observations)


def load_raw_observations() -> Tuple[List[Dict[str, Any]], str]:
    """Same as :func:`load_validated_observations` but from the raw
    (pre-data_quality) tree -- used by the quality endpoint, which needs
    to see what was rejected/flagged, not just what survived."""
    observations = _read_jsonl_dir(REPO_ROOT / "data" / "raw" / "fares")
    if not observations:
        return _generate_fallback_observations(), PROVENANCE_SYNTHETIC
    return observations, classify_provenance(observations)


def available_periods(observations: List[Dict[str, Any]]) -> List[str]:
    periods = {
        str(obs["flight_date"])[:7]
        for obs in observations
        if obs.get("flight_date")
    }
    return sorted(periods)


def observed_routes(observations: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    routes = {
        (obs["origin"], obs["destination"])
        for obs in observations
        if obs.get("origin") and obs.get("destination")
    }
    return sorted(routes)


def build_weights(observations: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, bool]:
    """Real DGCA-traffic-derived weights when every observed route maps to
    a known city (see index_engine.city_mapping.IATA_TO_CITY); synthetic
    (equal-weight) otherwise. Never raises -- a mapping gap degrades to
    synthetic rather than breaking the caller. Returns (weights_df, is_real)."""
    routes = observed_routes(observations)
    if not routes:
        return pd.DataFrame(columns=["origin", "destination", "weight"]), False
    try:
        weights_df, _diagnostics = traffic_mod.build_dgca_weights(DGCA_TRAFFIC_CSV, routes)
        if len(weights_df) == 0:
            raise ValueError("DGCA weights produced no rows for the observed routes.")
        return weights_df, True
    except Exception:
        route_codes = [f"{o}-{d}" for o, d in routes]
        return weighting_mod.generate_synthetic_weights(route_codes), False
