# Data Quality / Validation Layer

This is the interface between the scraper/database team and the Index
Engine, sitting one stage upstream of `docs/data_contract.md`:

```text
AIRLINE / OTA SCRAPERS
        |
RAW FARE OBSERVATIONS
        |
DATA QUALITY / VALIDATION   (this module — src/data_quality/)
        |
VALIDATED OBSERVATIONS
        |
AIRFARE INDEX ENGINE        (src/index_engine/ — unmodified, frozen at 88/88 tests)
```

It answers one question: **can we trust the fare observations coming from
the scraper?** It does not calculate the Airfare Price Index itself — that
remains entirely the index engine's job, methodology untouched.

## 1. Why this exists

The index engine already validates its input (`index_engine.validation`,
`index_engine.cleaning`) — required fields, parseable dates, positive
fares, duplicate `observation_id`s, statistical outliers. That is
correctness enforcement for the *math*: it guarantees the engine never
computes on garbage. It does not, and shouldn't have to, know anything
about *where the data came from* — which scraper, whether that scraper is
degrading, whether a "fare" of ₹5 is a data error or a genuine niche
promo, whether two rows are the same quote seen twice under different IDs.

That's this layer's job. It runs once, upstream of the engine, and
produces a report the scraper/backend team and the SIH judges can read
directly: how much of what came in is trustworthy, what's wrong with the
rest, and whether the *scraper itself* looks healthy.

## 2. Pipeline

```text
raw scraper output
   -> schema validation       (are the required columns even present?)
   -> field validation        (per-row REJECTION checks, one reason each)
   -> duplicate detection      (exact -> rejected, potential -> flagged)
   -> attention flags          (suspicious fare, unmapped city, ...)
   -> completeness scoring
   -> source health / route health
   -> quality score + grade
   -> DataQualityResult
```

Entry point: `data_quality.validate_fare_batch(raw_data, route_attempts=None,
config=None, reference_time=None, base_period=None, current_period=None)`.

Nothing is silently dropped. Every input row ends up `VALID`, `FLAGGED`, or
`REJECTED`, with a reason, recoverable per-row from
`DataQualityResult.record_results`.

## 3. Required vs. optional fields

Reused directly from `index_engine.config.REQUIRED_COLUMNS` — this module
does not define its own competing schema:

```text
observation_id, airline, origin, destination,
flight_date, booking_date, total_fare, currency
```

Optional (`data_quality.validation.OPTIONAL_COLUMNS`, matching
`docs/data_contract.md`):

```text
timestamp, source, fare_class, fare_type, base_fare,
taxes, fees, stops, duration, baggage, availability
```

## 4. VALID / FLAGGED / REJECTED

- **VALID** — passed every check, safe to pass onward with no caveats.
- **FLAGGED** — structurally fine, but worth a second look (unusually high
  fare, unmapped city, unknown airline, missing optional field, stale
  observation, unusual booking horizon, potential duplicate). A record can
  carry more than one flag.
- **REJECTED** — cannot safely enter the index pipeline. Exactly one
  reason code, first-match-wins in a fixed priority order (identity fields
  -> route validity -> dates -> currency -> fare).

`DataQualityResult.valid_observations` = **VALID + FLAGGED** (everything
not rejected), in the original raw field values — this is what gets handed
to `AirfarePriceIndex.calculate(...)`:

```python
quality_result = validate_fare_batch(raw_observations)
clean_data = quality_result.valid_observations

engine = AirfarePriceIndex(base_period="2026-01")
index_result = engine.calculate(observations=clean_data, current_period="2026-08")
```

Why flagged records still go through: a flag is an *attention marker for a
human/dashboard*, not a verdict that the record is wrong. See §8.

## 5. Rejection reason codes

| Code | Trigger |
|---|---|
| `MISSING_OBSERVATION_ID` | `observation_id` null/blank |
| `MISSING_AIRLINE` | `airline` null/blank |
| `MISSING_ORIGIN` | `origin` null/blank |
| `MISSING_DESTINATION` | `destination` null/blank |
| `INVALID_AIRPORT_CODE` | `origin`/`destination` present but not a well-formed 3-letter code |
| `SAME_ORIGIN_DESTINATION` | `origin == destination` (case-insensitive) |
| `INVALID_FLIGHT_DATE` | `flight_date` doesn't parse |
| `INVALID_BOOKING_DATE` | `booking_date` doesn't parse |
| `NEGATIVE_BOOKING_HORIZON` | `booking_date` after `flight_date` |
| `MISSING_CURRENCY` | `currency` null/blank |
| `NON_INR_CURRENCY` | `currency` present but not in `config.allowed_currencies` (default: INR only) |
| `NON_POSITIVE_FARE` | `total_fare` missing, zero, or negative |
| `EXACT_DUPLICATE` | same `observation_id`, or every other field identical (see §7) |
| `INVALID_SCHEMA` | one or more required columns entirely absent from the batch |

This is intentionally more granular than the index engine's own
`MISSING_REQUIRED_FIELD` — a dashboard wants to know *which* field is
missing, not just that something is. The engine still re-validates
whatever this layer forwards; that's defense-in-depth, not duplicated
logic to remove.

**Currency**: this is an INR-only prototype. A non-INR fare is rejected
rather than silently treated as INR or auto-converted — there is no FX
methodology in this project (see `docs/data_contract.md`). Extend
`config.allowed_currencies` if/when one exists.

**Airport codes**: format validity (3 letters) and *known-ness* (do we have
a verified DGCA mapping for it, via `index_engine.city_mapping`) are
different questions. A malformed code is rejected
(`INVALID_AIRPORT_CODE`); a well-formed code we simply don't have a
mapping for yet is flagged, not rejected (`UNMAPPED_LOCATION`, §6) — a
missing mapping is our gap, not evidence the scraper is wrong.

## 6. Flag reason codes

| Code | Trigger |
|---|---|
| `SUSPICIOUS_FARE` | fare falls well outside a robust (median/MAD) band for its route — see §8 |
| `UNMAPPED_LOCATION` | well-formed airport code, no entry in `index_engine.city_mapping` |
| `UNKNOWN_AIRLINE` | airline not in the hand-maintained `KNOWN_AIRLINES` reference list |
| `MISSING_OPTIONAL_FIELD` | one or more optional fields blank for this row |
| `STALE_OBSERVATION` | `timestamp` older than `config.stale_observation_max_age` (default 14 days) relative to the batch's newest timestamp, or an explicit `reference_time` |
| `UNUSUAL_BOOKING_HORIZON` | booked more than `config.unusual_booking_horizon_days` (default 330) before the flight — legitimate, just rare |
| `POTENTIAL_DUPLICATE` | same airline/origin/destination/flight_date/booking_date(/source), fare within `config.potential_duplicate_fare_tolerance_pct` (default 1%) of another row in the group — see §7 |

Reference lists (`data_quality/reference_data.py`) are deliberately small
and hand-maintained, same philosophy as `index_engine.city_mapping`: an
unrecognized value means "we don't recognize it yet," not "it's wrong."
Add to the list rather than teaching the checker to reject unfamiliar-but-
real values.

## 7. Duplicate handling

**Exact duplicate** (rejected): same `observation_id` seen again, *or*
every other field identical (the full row, `observation_id` aside, reduced
to a string key and compared). Either one adds zero new information.

**Potential duplicate** (flagged, never auto-rejected): same
airline/origin/destination/flight_date/booking_date(/source if present),
fare within a small tolerance of another row already seen in that group.
This is *not* auto-removed — near-identical fares on the same route/date
can legitimately be two different real quotes (e.g. two seats at the same
published fare), and collapsing them without a human/analyst decision
would understate real sample size. The rule that produced the flag is
fully documented here rather than left as an opaque judgment call.

```text
duplicate_count = exact_duplicate_count + potential_duplicate_count
```

## 8. Suspicious fare vs. statistical outlier — the important distinction

**Data Quality detects impossible/suspicious records. Statistical cleaning
determines statistical outliers.** These are deliberately different
mechanisms with different authority:

- This layer's `SUSPICIOUS_FARE` flag is a coarse, wide, per-route sanity
  net: robust median/MAD bounds with a much wider multiplier
  (`config.fare_sanity_mad_multiplier`, default 6.0×) than the index
  engine's own outlier detector. Its job is to catch obvious scraping
  errors (a fare of ₹5, a decimal-point slip turning ₹5,000 into
  ₹5,00,000) — not to make the final call on whether an unusual-but-real
  fare belongs in the index.
- It uses **no fixed rupee threshold**. "₹50,000 = invalid" is exactly the
  kind of arbitrary hard-code this project's methodology doesn't define
  and this layer deliberately avoids. Bounds are relative to the route's
  own fare distribution within the batch.
- `index_engine.cleaning`'s `OUTLIER_IQR`/`OUTLIER_MAD`/`OUTLIER_PERCENTILE`
  detection (configurable via `IndexConfig`) runs *after* this layer, on
  data this layer already passed through, grouped by route **and period**.
  That is the authoritative statistical call the index methodology relies
  on — this layer never removes a record for being an outlier, only flags
  it for attention.
- A ₹2,00,000 fare might be a legitimate premium fare, a statistical
  outlier, or a scraping error. This layer says "SUSPICIOUS — someone
  should look at this." Only the engine's statistical cleaning, as part of
  index calculation, decides whether it's actually excluded.

If a route/route-period group is too small to say anything statistically
meaningful (`config.fare_sanity_group_min_size`, default 5), the layer
falls back to whole-batch statistics, and if even that isn't enough, it
simply does not flag on fare for that record — a documented limitation,
not a silent guess.

## 9. Completeness

Computed per batch over **all received records**, not just survivors:

```text
completeness_rate = records_with_all_required_fields / total_records
```

Optional-field gaps are tracked separately
(`records_missing_optional_fields`) and, by default, do **not** reduce
`completeness_rate` — set `config.require_optional_fields_for_completeness`
if a stricter mode is ever wanted. A record missing every optional
column entirely (the scraper never sent them) is a valid, if minimal,
prototype scraper contract.

## 10. Quality score and grade

Transparent weighted sum, not an opaque/learned score:

```text
quality_score = 100 * (
      0.25 * completeness_rate
    + 0.35 * validity_rate
    + 0.15 * (1 - duplicate_rate)
    + 0.10 * schema_compliance_rate
    + 0.15 * source_success_rate
)
```

Weights live in `DataQualityConfig.quality_score_weights`
(`QualityScoreWeights`, must sum to 1.0) and are trivially overridable.
`source_success_rate` (route-request success, from an optional
`route_attempts` log — see §11) defaults to a neutral 1.0 when that
optional input wasn't supplied, so its absence doesn't unfairly tank a
batch's score.

Grade bands:

| Score | Grade |
|---|---|
| 95–100 | EXCELLENT |
| 90–94 | GOOD |
| 75–89 | WARNING |
| <75 | POOR |

**These are explicitly PROTOTYPE thresholds for this SIH build, not an
official statistical standard** — same caveat the index engine attaches to
its own outlier thresholds and route-coverage bands.

## 11. Source health ("is the scraper actually working?")

`DataQualityResult.source_health`: one `SourceHealth` per distinct
`source` value (falls back to a single `"UNKNOWN_SOURCE"` group if the
batch has no `source` column at all).

Always derivable from the observations themselves:
`observations_received`, `valid_observations`, `flagged_observations`,
`rejected_observations`, `observation_validity_rate`, and — if `timestamp`
is present — `oldest_observation`/`newest_observation`/`data_age_seconds`.

**Only** derivable with an optional `route_attempts` input — a log of what
the scraper *tried*, since fare observations alone can't say "we asked for
BLR-IXL and got nothing back":

```python
route_attempts = [
    {"source": "airline_A", "routes_requested": 50, "routes_successful": 47,
     "routes_attempted": ["BLR-DEL", "DEL-BOM", ...]},  # routes_attempted is optional, enables overall_route_coverage
]
result = validate_fare_batch(raw_data, route_attempts=route_attempts)
```

Without it, `routes_requested`/`routes_successful`/`routes_failed`/
`route_success_rate` are `None` — never `0`, since `0` would falsely claim
total failure this layer has no basis to claim.

**Status classification** (prototype thresholds,
`config.degraded_validity_rate_threshold` /
`config.degraded_route_success_rate_threshold`):

- `FAILED` — zero observations received, or a confirmed 0% route success rate.
- `DEGRADED` — validity rate or route success rate below threshold.
- `HEALTHY` — otherwise.

A source that returned data, all of which happened to be rejected, is
`DEGRADED` (it produced *something*), not `FAILED` — `FAILED` is reserved
for "the source gave us nothing at all."

## 12. Route health

`DataQualityResult.route_health`: one `RouteHealth` per observed
origin-destination pair — `observations_total`, `observations_valid` (VALID
+ FLAGGED), `observations_rejected`, `route_quality_rate`,
`data_completeness`, and (only if `base_period`/`current_period` are
passed to `validate_fare_batch`) `has_base_period_data` /
`has_current_period_data`.

This **complements**, and does not replace,
`index_engine.quality`/`RouteIndexResult.status`
(`NO_BASE_DATA`/`INSUFFICIENT_DATA`/...), which answers "could a
*statistical index* be computed for this route." `RouteHealth` answers
"do this route's *raw observations* look trustworthy" — a route can have
excellent data quality here and still show `INSUFFICIENT_DATA` in the
engine's own output if it simply has too few surviving points once
grouped by period, or vice versa.

## 13. Integration with the index engine

```python
from data_quality import validate_fare_batch
from index_engine import AirfarePriceIndex

quality_result = validate_fare_batch(raw_data, route_attempts=route_attempts)

engine = AirfarePriceIndex(base_period="2026-01")
index_result = engine.calculate(
    observations=quality_result.valid_observations,
    current_period="2026-08",
)
```

`index_engine`'s methodology, statistical thresholds, and test suite
(88/88) are untouched by this module — it only decides what gets *handed
to* `AirfarePriceIndex.calculate`, never how the index itself is computed.

## 14. Limitations (prototype, explicitly)

- `SUSPICIOUS_FARE` cannot flag anything in a route/batch too small to
  establish a robust distribution (fewer than
  `config.fare_sanity_group_min_size` points, batch-wide fallback
  included) — documented, not silently guessed around.
- `source_success_rate` / `routes_requested` / route coverage require the
  scraper to separately supply a `route_attempts` log; fare observations
  alone cannot reconstruct "routes we asked for and got nothing back."
- `KNOWN_AIRLINES` / `KNOWN_AIRPORTS` (via `index_engine.city_mapping`) are
  small, hand-maintained lists — a legitimate new/rebranded carrier or a
  newly-covered airport will be flagged, not rejected, until added.
- Currency handling is INR-only by design; no FX conversion exists in this
  project, so any non-INR fare is rejected rather than guessed at.
- Quality score weights and grade bands are prototype defaults for this
  SIH build, not a validated or peer-reviewed standard.
