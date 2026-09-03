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

REPO_ROOT = Path(__file__).resolve().parents[2]

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


def _is_all_mock(observations: List[Dict[str, Any]]) -> bool:
    """Whether every observation is explicitly flagged as mock/synthetic
    scraper output. Empty is treated as "no real data" (True), not "real
    by absence" -- see docs/scraper.md "Raw vs validated storage"."""
    if not observations:
        return True
    return all(obs.get("is_mock", True) for obs in observations)


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


def load_validated_observations() -> Tuple[List[Dict[str, Any]], bool]:
    """Returns (observations, is_real). ``is_real`` is True only when at
    least one persisted, non-mock validated observation exists -- see
    ``_is_all_mock``. Falls back to a synthetic demo dataset (is_real=False)
    when nothing has been scraped and validated yet."""
    observations = _read_jsonl_dir(REPO_ROOT / "data" / "validated" / "fares")
    if not observations:
        return _generate_fallback_observations(), False
    return observations, not _is_all_mock(observations)


def load_raw_observations() -> Tuple[List[Dict[str, Any]], bool]:
    """Same as :func:`load_validated_observations` but from the raw
    (pre-data_quality) tree -- used by the quality endpoint, which needs
    to see what was rejected/flagged, not just what survived."""
    observations = _read_jsonl_dir(REPO_ROOT / "data" / "raw" / "fares")
    if not observations:
        return _generate_fallback_observations(), False
    return observations, not _is_all_mock(observations)


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
