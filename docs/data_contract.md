# Data Contract — Index Engine Input

This is the interface contract between the scraper/database team and the
Index Engine. It exists so both sides can build independently: the
scraper doesn't need to know how the index math works, and the engine
doesn't need to know how the data was collected.

The engine accepts a pandas DataFrame or a list of dicts with one row per
fare observation (one scraped/quoted fare, not one route).

## Required fields

The engine raises immediately if any of these columns are absent. Rows
with a missing/invalid *value* in one of these are not dropped silently —
they are rejected with a recorded reason (see "What happens when a
required value is missing or invalid" below).

| Field | Type | Notes |
|---|---|---|
| `observation_id` | string | Must be unique per observation. Duplicates (same id seen twice) are removed and counted, keeping the first occurrence. |
| `airline` | string | Non-empty. Not currently used to split groups (see §"Fields accepted but not yet used"). |
| `origin` | string (IATA code) | Case-insensitive, upper-cased internally. |
| `destination` | string (IATA code) | Must differ from `origin`. |
| `flight_date` | date (`YYYY-MM-DD` or ISO) | Determines which monthly `period` the observation belongs to. |
| `booking_date` | date (`YYYY-MM-DD` or ISO) | Must be on or before `flight_date`. Used to derive `booking_horizon_days`. |
| `total_fare` | number | Must be > 0. This is the standardized comparable fare by default — see `IndexConfig.fare_field` to change. |
| `currency` | string | Non-empty. **Not currently converted** — see limitations below. |

## Optional fields (accepted, currently informational only)

These are accepted if present and safe to omit — the scraper does **not**
need to reproduce them just to satisfy the engine. They exist in the
schema for forward compatibility (e.g. a future per-fare-class index) but
today they do not change any calculation:

`timestamp, source, fare_class, fare_type, base_fare, taxes, fees, stops,
duration, baggage, availability`

If your scraper naturally produces some of these, send them anyway —
no harm, and it means we don't have to re-integrate later if the
methodology grows to use them (e.g. splitting by `fare_class`).

## What happens when a required value is missing or invalid

Nothing is silently dropped. Every rejected row is tagged with exactly one
reason and counted in `IndexResult.cleaning_report`:

| Reason | Trigger |
|---|---|
| `MISSING_REQUIRED_FIELD` | `observation_id`, `airline`, `origin`, `destination`, or `currency` is null/blank |
| `INVALID_DATE` | `flight_date` or `booking_date` doesn't parse |
| `INVALID_FARE` | `total_fare` is null, zero, or negative |
| `SAME_ORIGIN_DESTINATION` | `origin == destination` |
| `IMPOSSIBLE_BOOKING_HORIZON` | `booking_date` is after `flight_date` |
| `DUPLICATE` | `observation_id` seen more than once |
| `OUTLIER_IQR` / `OUTLIER_MAD` / `OUTLIER_PERCENTILE` | statistical outlier within its route+period group (method configurable) |

A route that ends up with too few surviving observations for a given
period (default: fewer than 3, via
`IndexConfig.min_observations_per_route_period`) is not silently used —
see `RouteIndexResult.status`.

## What happens when currency isn't INR

Not handled in this prototype. All fares are assumed to be in the same
currency (INR for the Indian domestic routes this project targets). If
the scraper ever needs to mix currencies, that conversion must happen
**before** data reaches the engine — this is explicitly out of scope here
and called out in `docs/methodology.md` limitations.

## Route weights (separate input, optional)

Not part of the fare observation schema. Passed separately as a DataFrame:

| Field | Required | Notes |
|---|---|---|
| `origin`, `destination` | yes | Defines the route |
| `weight` | yes | Relative importance; normalized internally, doesn't need to sum to 1 |
| `effective_from`, `effective_to` | no | Date range the weight applies to; omit for "always" |
| `source` | no | Free text provenance tag |

If omitted entirely, the engine generates synthetic placeholder weights
tagged `SYNTHETIC_DEMO_ONLY` from whatever routes appear in the
observations — fine for demo purposes, **not to be presented as real**.

## Traffic data contract (for DGCA-derived weights)

Separate from fare observations and route weights. `index_engine.traffic`
accepts the DGCA domestic city-pair CSV as delivered — see
`data/traffic/README.md` for full provenance:

| Field | Required | Notes |
|---|---|---|
| `Year` | yes | Numeric |
| `Month` | yes | 1–12 |
| `City1`, `City2` | yes | Full city names as published (not IATA codes) |
| `PaxToCity2` | yes | Passengers City1 → City2 that month |
| `PaxFromCity2` | yes | Passengers City2 → City1 that month |

Rejection reasons (nothing silently dropped): `MISSING_CITY`,
`SAME_ORIGIN_DESTINATION`, `INVALID_MONTH`, `INVALID_YEAR`,
`INVALID_PASSENGER_COUNT` (either direction null/negative — the whole
record is rejected rather than guessing which half is salvageable),
`DUPLICATE_TRAFFIC_RECORD`.

`index_engine.city_mapping` translates between IATA codes (used by fare
observations) and DGCA city names — a small, hand-verified dictionary,
not fuzzy matching. Adding a new route requires adding and verifying a
mapping entry first.

## Affordability input contract (optional)

`index_engine.affordability` accepts an income/wage series completely
independent of fare observations:

| Field | Required | Notes |
|---|---|---|
| `period` | yes | `YYYY-MM` |
| `indicator` | yes | e.g. `"income_index"` — lets multiple indicator series coexist |
| `value` | yes | Index value, same base-period convention as the airfare index |
| `source` | no | Provenance tag; use `SYNTHETIC_DEMONSTRATION_DATA` for anything not a real validated series |

If omitted, or if the requested period/indicator isn't found,
`AffordabilityResult.status` is `DATA_UNAVAILABLE` — the core price index
is entirely unaffected either way.

## Output contract

`AirfarePriceIndex.calculate(...)` returns an `IndexResult` dataclass;
call `.to_dict()` to get a plain, JSON-serializable dict (no custom
classes, safe for any backend to `json.dumps` directly). See
`docs/methodology.md` §12 for the full field list and route status
values, and `api/schemas.py` for the equivalent typed HTTP response shape.
