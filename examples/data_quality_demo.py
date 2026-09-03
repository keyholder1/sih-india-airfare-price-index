"""Data Quality layer demo, using SYNTHETIC DEMONSTRATION DATA.

Starts from the same synthetic fare generator the index-engine demos use
(``generate_sample_fares.generate``), then deliberately injects the kinds
of problems a real scraper produces — missing fields, bad dates, zero/
negative fares, a non-INR quote, exact and near-duplicate quotes, an
unmapped airport, an unrecognized carrier, and a stale observation — so the
report below has something of everything to show.

None of these numbers represent real airline pricing or a real scraper run.

Run from the repo root:

    python examples/data_quality_demo.py
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from data_quality import validate_fare_batch
from generate_sample_fares import generate

random.seed(7)


def synthesize_scrape_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Replace ``timestamp`` with a plausible "when the scraper captured
    this quote" value — clustered in the last few days, independent of the
    fare's own booking_date/flight_date. The generator's original timestamp
    IS booking_date (fine for the index engine, which ignores timestamp
    entirely), but that spans months in one batch and would make almost
    every row look "stale" here for a reason that has nothing to do with
    actual scraper freshness. SYNTHETIC DEMONSTRATION DATA."""
    df = df.copy()
    now = pd.Timestamp.now()
    df["timestamp"] = [
        (now - pd.Timedelta(hours=random.uniform(0, 72))).isoformat() for _ in range(len(df))
    ]
    return df


def inject_quality_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Corrupt a small, fixed fraction of an otherwise-clean synthetic batch
    so the demo has REJECTED and FLAGGED records to report on. SYNTHETIC
    DEMONSTRATION DATA — these defects are manufactured, not observed."""
    rows = df.to_dict("records")
    n = len(rows)

    def pick(k):
        return random.sample(range(n), k)

    for i in pick(8):
        rows[i]["total_fare"] = 0
    for i in pick(6):
        rows[i]["total_fare"] = -abs(rows[i]["total_fare"])
    for i in pick(5):
        rows[i]["origin"] = rows[i]["destination"]
    for i in pick(5):
        rows[i]["booking_date"], rows[i]["flight_date"] = rows[i]["flight_date"], rows[i]["booking_date"]
    for i in pick(4):
        rows[i]["observation_id"] = ""
    for i in pick(4):
        rows[i]["currency"] = random.choice(["USD", "EUR", "GBP"])
    for i in pick(6):
        rows[i]["origin"] = "XYZ"  # well-formed but unmapped
    for i in pick(6):
        rows[i]["airline"] = "NewRegionalCarrier"

    # Exact duplicates: clone a handful of otherwise-clean rows verbatim
    # (same observation_id -> caught as EXACT_DUPLICATE).
    for i in pick(6):
        rows.append(dict(rows[i]))

    # Potential duplicates: same route/date/source/airline, fare off by <1%.
    for i in pick(5):
        clone = dict(rows[i])
        clone["observation_id"] = clone["observation_id"] + "_NEARDUP"
        clone["total_fare"] = round(clone["total_fare"] * 1.003, 2)
        rows.append(clone)

    # A handful of extreme fares for SUSPICIOUS_FARE to catch (distinct from
    # the *_OUTLIER rows generate_sample_fares() already injects for the
    # index engine's own statistical outlier detection).
    for i in pick(5):
        rows[i] = dict(rows[i])
        rows[i]["observation_id"] = rows[i]["observation_id"] + "_SUSPICIOUS"
        rows[i]["total_fare"] = round(rows[i]["total_fare"] * random.uniform(15, 25), 2)

    # Stale observations far outside the batch's normal (last-3-days) scrape
    # window. Matches the same isoformat()-with-microseconds precision as
    # the rest of the column — a mismatched precision (e.g. a bare
    # "YYYY-MM-DDTHH:MM:SS" literal next to microsecond timestamps) can trip
    # pandas' to_datetime format inference into silently coercing the odd
    # one out to NaT instead of parsing it.
    stale_timestamp = (pd.Timestamp.now() - pd.Timedelta(days=400)).isoformat()
    for i in pick(15):
        rows[i]["timestamp"] = stale_timestamp

    return pd.DataFrame(rows)


def bar(count: int, total: int, width: int = 30) -> str:
    if total == 0:
        return " " * width
    filled = round(width * count / total)
    return "#" * filled + "-" * (width - filled)


def main() -> None:
    # A data-quality batch is realistically "what one scrape cycle sent
    # back", not the index engine's full multi-month backtest window — take
    # the most recent slice so STALE_OBSERVATION means something (otherwise
    # every early-period row would look stale next to the newest one).
    fares = generate()
    fares = fares[fares["flight_date"] >= "2026-06-01"].reset_index(drop=True)
    fares = synthesize_scrape_timestamps(fares)
    dirty = inject_quality_issues(fares)

    route_attempts = [
        {"source": "airline_site", "routes_requested": 10, "routes_successful": 10},
        {"source": "mmt", "routes_requested": 10, "routes_successful": 9},
        {"source": "cleartrip", "routes_requested": 10, "routes_successful": 8},
        {"source": "goibibo", "routes_requested": 10, "routes_successful": 10},
    ]

    result = validate_fare_batch(dirty, route_attempts=route_attempts)

    print("=" * 60)
    print("DATA QUALITY REPORT  (SYNTHETIC DEMONSTRATION DATA)")
    print("=" * 60)
    print(f"Records received:  {result.records_received:>8,}")
    print(f"Valid:             {result.records_valid:>8,}")
    print(f"Flagged:           {result.records_flagged:>8,}")
    print(f"Rejected:          {result.records_rejected:>8,}")
    print()
    print(f"Completeness:      {result.completeness_rate * 100:>7.1f}%")
    print(f"Validity:          {result.validity_rate * 100:>7.1f}%")
    print(f"Duplicate rate:    {result.duplicate_rate * 100:>7.1f}%  "
          f"(exact={result.exact_duplicate_count}, potential={result.potential_duplicate_count})")
    print()
    print(f"Quality Score:     {result.quality_score:>7.1f}")
    print(f"Quality Grade:     {result.quality_grade}")
    print("(prototype monitoring metrics — not an official statistical standard)")
    print()

    print("-" * 60)
    print("TOP REJECTION REASONS")
    print("-" * 60)
    top_rejections = sorted(result.rejection_reasons.items(), key=lambda kv: -kv[1])[:6]
    max_rejection = max((c for _, c in top_rejections), default=0)
    for reason, count in top_rejections:
        print(f"{reason:<28} {count:>4}  {bar(count, max_rejection)}")
    print()

    print("-" * 60)
    print("TOP FLAG REASONS")
    print("-" * 60)
    top_flags = sorted(result.flag_reasons.items(), key=lambda kv: -kv[1])[:6]
    max_flag = max((c for _, c in top_flags), default=0)
    for reason, count in top_flags:
        print(f"{reason:<28} {count:>4}  {bar(count, max_flag)}")
    print()

    print("-" * 60)
    print("SOURCE HEALTH")
    print("-" * 60)
    for s in result.source_health:
        route_success = f"{s.route_success_rate * 100:5.1f}%" if s.route_success_rate is not None else "  n/a"
        print(
            f"{s.source:<16} status={s.status:<9} "
            f"validity={s.observation_validity_rate * 100:5.1f}%  route_success={route_success}"
        )
    print()

    print("-" * 60)
    print("ROUTE HEALTH (top 10 by observation count)")
    print("-" * 60)
    top_routes = sorted(result.route_health, key=lambda r: -r.observations_total)[:10]
    for r in top_routes:
        print(f"{r.route:<10} obs={r.observations_total:>4}  quality={r.route_quality_rate * 100:5.1f}%")
    print()

    if result.overall_route_success_rate is not None:
        print(f"Overall scraper route success rate: {result.overall_route_success_rate * 100:.1f}%")
    print()
    print(f"Records safe to pass to AirfarePriceIndex: {len(result.valid_observations):,}")
    print("(VALID + FLAGGED — rejected rows never reach the index engine;")
    print(" the engine's own statistical outlier detection remains the")
    print(" authority on any FLAGGED SUSPICIOUS_FARE record.)")


if __name__ == "__main__":
    main()
