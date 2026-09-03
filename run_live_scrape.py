"""One-off: run a real SCRAPER_MODE=live scrape (SerpApi/Google Flights)
for all Tier-1 routes (top 20 by national traffic weight), and persist it
into data/raw/fares + data/validated/fares in the exact shape
src/engine/data_access.py reads -- so the API serves real fares instead
of a smaller/mock run.

20 routes x 6 booking-horizon buckets = 120 SerpApi calls. Check
https://serpapi.com/account?api_key=... first if you're unsure of
remaining monthly quota -- it doesn't consume a search credit.

Run from the repo root: python run_live_scrape.py
"""
from __future__ import annotations

import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from data_quality import validate_fare_batch
from scraper import ScraperConfig, generate_booking_horizon_dates, load_routes, run_scrape
from scraper.runner import run_scrape as _run_scrape  # noqa: F401 (import check)
from scraper.storage import write_raw_run, write_validated_run, write_run_report


def main() -> None:
    assert os.environ.get("SERPAPI_API_KEY"), "SERPAPI_API_KEY not set -- check .env"

    routes = load_routes(tiers=(1,))
    dates = generate_booking_horizon_dates(date(2026, 9, 3))
    config = ScraperConfig(mode="live", tiers=(1,), min_interval_seconds=0.5, max_retries=2)

    print(f"Scraping {len(routes)} routes x {len(dates)} booking-horizon dates = "
          f"{len(routes) * len(dates)} SerpApi calls...")
    raw_observations, report = run_scrape(config, routes=routes, dates=dates)

    print("\n--- Scraper run report ---")
    print(report.to_text())

    n_real = sum(1 for o in raw_observations if not o.get("is_mock", False))
    print(f"\nObservations collected: {len(raw_observations)} (real={n_real})")

    if not raw_observations:
        print("No observations collected -- leaving existing data files untouched.")
        return

    raw_path = write_raw_run(report.run_id, raw_observations)
    print(f"Wrote raw run: {raw_path}")

    dq_result = validate_fare_batch(raw_observations, route_attempts=report.to_route_attempts())
    print(f"Data quality: received={dq_result.records_received} valid={dq_result.records_valid} "
          f"flagged={dq_result.records_flagged} rejected={dq_result.records_rejected} "
          f"score={dq_result.quality_score} ({dq_result.quality_grade})")

    validated_path = write_validated_run(report.run_id, dq_result.valid_observations)
    print(f"Wrote validated run: {validated_path}")

    report_path = write_run_report(report)
    print(f"Wrote run report: {report_path}")


if __name__ == "__main__":
    main()
