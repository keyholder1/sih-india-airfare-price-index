"""End-to-end demonstration: route configuration -> scraper -> raw
observations -> Data Quality -> Index Engine -> index result.

This is the single "does the whole pipeline actually fit together" demo
item 23 of the scraper brief asks for. It runs in ``SCRAPER_MODE=mock`` by
default (set the environment variable to ``live`` to see the honest
zero-results, all-SOURCE_UNAVAILABLE outcome instead — see
docs/scraper.md §2 for why nothing is wired up live yet).

Run from the repo root:

    python examples/scraper_demo.py
    SCRAPER_MODE=live python examples/scraper_demo.py
"""

from __future__ import annotations

import logging
import os
from datetime import date

from data_quality import validate_fare_batch
from index_engine import AirfarePriceIndex, IndexConfig
from scraper import ScraperConfig, generate_booking_horizon_dates, load_routes, run_scrape
from scraper.models import ScrapeRunReport
from scraper.storage import write_collection_json

logging.getLogger("scraper").setLevel(logging.INFO)

BASE_PERIOD = CURRENT_PERIOD = "2026-09"


def main() -> None:
    mode = os.environ.get("SCRAPER_MODE", "mock")
    print(f"=== Scraper demo (SCRAPER_MODE={mode}) ===\n")

    routes = load_routes(tiers=(1,))[:5]
    dates = generate_booking_horizon_dates(date(2026, 9, 1))
    config = ScraperConfig(mode=mode, tiers=(1,), min_interval_seconds=0.0, max_retries=1)

    print(f"Route configuration: {len(routes)} routes (Tier 1), {len(dates)} booking-horizon dates\n")
    raw_observations, report = run_scrape(config, routes=routes, dates=dates)

    print("\n--- Scraper run report ---")
    print(report.to_text())

    json_path = write_collection_json(report, raw_observations, base_dir="data")
    print(f"\n--- JSON collection envelope written ---\n{json_path}")

    is_real = len(raw_observations) > 0 and all(not o.get("is_mock", False) for o in raw_observations)
    has_data = len(raw_observations) > 0
    label = "REAL LIVE SCRAPED DATA" if is_real else ("MOCK DEMONSTRATION DATA" if has_data else "NO DATA COLLECTED")
    print(f"\n>>> These observations are: {label} <<<\n")

    if not raw_observations:
        print("No observations collected - nothing to validate or index.")
        print("(Expected in live mode today: every source is SOURCE_UNAVAILABLE - see docs/scraper.md section 2.)")
        return

    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    print("--- Data Quality result ---")
    print(f"received={dq_result.records_received} valid={dq_result.records_valid} "
          f"flagged={dq_result.records_flagged} rejected={dq_result.records_rejected}")
    print(f"quality_score={dq_result.quality_score} ({dq_result.quality_grade})")
    if dq_result.rejection_reasons:
        print(f"rejection_reasons={dq_result.rejection_reasons}")
    if dq_result.flag_reasons:
        print(f"flag_reasons={dq_result.flag_reasons}")

    engine = AirfarePriceIndex(
        base_period=BASE_PERIOD,
        config=IndexConfig(base_period=BASE_PERIOD, min_observations_per_route_period=1),
    )
    index_result = engine.calculate(dq_result.valid_observations, current_period=CURRENT_PERIOD)

    print("\n--- Index Engine result ---")
    print(f"national_index={index_result.national_index} routes_covered={index_result.routes_covered}/{index_result.routes_total}")
    print(f"quality_flags={index_result.quality_flags}")

    print(f"\n>>> Reminder: this run used {label}. <<<")


if __name__ == "__main__":
    main()
