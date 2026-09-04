# Natural Event & Weather Context Layer

**Status: SIH prototype, added as an additive context layer alongside
the existing News & Event Context module (`docs/news_context.md`).**
This document describes the `eonet_*` modules (real events) and the
`weather_*`/`openweather_client` modules (live conditions). Both answer
variants of the same question the news layer already asks:

> "Was there something real, nearby, and around the right time that
> might explain this route's fare movement?"

Neither ever answers that question with certainty, and neither ever
changes the index. See [Non-causality](#5-non-causality-the-most-important-rule)
before wiring either into any user-facing text.

---

## 1. Where this sits in the pipeline

```
Airline / OTA fare sources
  -> Scraper
  -> Data Quality Validation
  -> Airfare Price Index Engine   (src/index_engine/index.py — FROZEN, unchanged)
  -> Analytics
  -> Backend API
  -> Frontend Dashboard

EONET Natural Events (NASA, real, keyless)
  -> eonet_context.EonetContextService
       +
OpenWeatherMap current conditions (real, key required)
  -> weather_context.WeatherContextService
  -> merged into the SAME route context response
       as news (api/routes/news.py) and the SAME
       compact national list pattern as
       /analytics/data-quality, /analytics/forecast
  -> Backend API
  -> Frontend Dashboard
```

Both layers are **pure consumers** of index-engine output, exactly like
the news layer. `eonet_matching.py` imports `RouteMovement` from
`news_models.py` (reused, not duplicated) to read a route's
already-computed `mom` percentage change; nothing here imports, calls,
or modifies `index.py`, `aggregation.py`, `weighting.py`,
`contribution.py`, or any other file that produces an index number.
**Nothing in `index_engine`'s core modules imports anything from
`eonet_*`/`weather_*` either** — verified by an explicit test
(`tests/test_eonet_context.py::test_index_engine_modules_never_import_eonet`,
which walks `index.py`/`aggregation.py`'s own AST) rather than just
asserted in prose.

## 2. What EONET is, and why we use it

[NASA EONET](https://eonet.gsfc.nasa.gov/) (Earth Observatory Natural
Event Tracker) is a public, curated feed of significant natural events
worldwide — wildfires, storms, floods, volcanic activity, and more —
each with a category, a title, one or more dated geographic positions,
and a source link. It's maintained by NASA's Earth Observatory team,
aggregating from agencies like GDACS, USGS, and national disaster
services.

We use it because a route's fare can move for reasons a pure statistics
engine can't see: an airport disrupted by a storm, a wildfire affecting
regional demand, a flood cutting off ground transport that shifts
travelers to flights. EONET gives us **real, dated, located** events to
check a movement against — not a guess, and not News's string-matched
headlines, but actual coordinates and dates from a scientific tracking
system.

**Verified live (2026-09-04):** EONET's REST API
(`https://eonet.gsfc.nasa.gov/api/v3`) requires **no credential at
all** — a plain unauthenticated `GET /events` returns real data. This
was confirmed empirically, not assumed from documentation, before any
code was written. `EONET_API_KEY` exists in `.env.example` purely for
forward-compatibility and this project's blanket policy (every external
credential comes from an environment variable, never hard-coded) — it
is not required and, if unset, nothing is sent.

## 3. Event categories used

EONET's own category vocabulary (`GET /api/v3/categories`, verified
live) has 13 entries. This project queries a deliberate subset —
`eonet_context.RELEVANT_CATEGORIES` — chosen for plausible relevance to
airline operations or travel demand:

| Category | Why included |
|---|---|
| `severeStorms` | Direct flight-disruption risk. |
| `wildfires` | Smoke/visibility, regional demand shifts. |
| `volcanoes` | Ash cloud grounding risk. |
| `floods` | Ground-transport disruption, demand shift to air. |
| `tempExtremes` | Extreme heat/cold operational constraints. |
| `dustHaze` | Visibility-driven delays/cancellations. |
| `earthquakes` | Airport/infrastructure disruption risk. |

Excluded, and why: `seaLakeIce`, `waterColor` (no plausible link to
Indian domestic air travel), `manmade` (too broad/ambiguous to score
meaningfully as one category), `drought`, `landslides`, `snow` (not
typically flight-operationally relevant the way the above are, for
routes covered by this project). No category is ever invented — every
id used is a verified real EONET category id
(`eonet_models.EONET_CATEGORIES`, cross-checked by
`tests/test_eonet_context.py::test_relevant_categories_are_real_eonet_category_ids`).

## 4. Geographic and temporal matching

### Geometry: only `Point`, deliberately

EONET events carry a `geometry` array of dated positions. Two shapes
were observed live: `Point` (a single `[lon, lat]` pair — verified
against real India-region wildfire events, e.g. `[82.674, 21.844]` for
"Wildfire in India", correctly falling inside India's real
longitude/latitude range) and `Polygon` (observed for some flood
events, e.g. Pakistan/Nepal floods, as a boundary ring). The axis
ordering for `Polygon` coordinates could **not** be confirmed with
confidence in this session — rather than risk silently swapping
latitude and longitude for those events, `NaturalEvent.from_raw`
**excludes any event whose geometry array contains no `Point` entry**.
This is a stated, documented limitation, not a silent bug: a flood
event that happens to also carry a `Point` entry is still used (this
was observed live for at least one real flood near Mumbai); a
Polygon-only event is not matched at all.

### Geographic proximity

`eonet_matching.haversine_km` computes the real great-circle distance
(km) from an event to the route's origin **and** destination airports,
using the same `index_engine.geo_metadata.CITY_COORDINATES` table the
dashboard's own India map already uses (`route_map_objects`) — no
second coordinate reference was introduced. The closer of the two
airports is used. A configurable radius,
`EonetMatchingConfig.radius_km` (default **300 km** —
`DEFAULT_EVENT_RADIUS_KM`), bounds relevance: within it, the score
decays linearly from 1.0 (at the airport) to 0.0 (at the radius edge);
beyond it, the geographic component is exactly 0.

300 km was chosen (and documented, not left as an unexplained magic
number) to cover "affects the metro area and its usual catchment" — a
cyclone making landfall near a city, a wildfire in the surrounding
region — without stretching to "somewhere in the same half of the
country."

### Temporal proximity

The days between the event's date and the route movement's `as_of`
(the same movement timestamp the news layer uses) are compared against
a configurable window, `EonetMatchingConfig.time_window_days` (default
**14 days** — `DEFAULT_EVENT_TIME_WINDOW_DAYS`, wider than the news
layer's 10-day window since a natural event's effect on bookings can
plausibly persist a little longer than one news cycle). Within the
window, the score decays linearly from 1.0 (same day) to 0.0 (at the
window edge); beyond it, the temporal component is exactly 0.

Separately, `eonet_context.DEFAULT_LOOKBACK_DAYS` (90 days) bounds what
is *fetched* from EONET at all (via its own `days` query parameter) —
wider than the 14-day *matching* window on purpose, so a single India-
wide fetch (cached in-process, see §7) can serve matching for any route
movement in roughly the last ~76 days without a second request.

## 5. Relevance scoring

`eonet_matching.score_event` combines the two signals above as a
weighted sum, exactly like `news_matching.score_article`'s approach —
transparent, documented constants, not a black box or a learned model:

```
relevance = 0.6 * geographic_score + 0.4 * temporal_score
```

(`WEIGHT_GEOGRAPHIC = 0.6`, `WEIGHT_TEMPORAL = 0.4`.) An event outside
**both** the radius and the window scores exactly 0 — not "somewhat
relevant." `eonet_matching.rank_events` then de-duplicates by event id,
filters to `relevance_score >= min_relevance` (default 0.35), and
returns the top `top_n` (default 5), highest-relevance first.

Every match carries its own `relevance_reason` — plain-language strings
like `"within 300km of destination (85km away)"` — so a judge (or a
future maintainer) can see *why* a given event surfaced without
re-deriving the score by hand.

## 6. Non-causality — the most important rule

This layer answers **"was there a plausible contextual factor,"** never
**"this event caused the fare to move."** Every result carries the same
`CAUSATION_DISCLAIMER` the news layer already uses:

> "This is contextual evidence only, not a causal explanation. The
> events below coincided with the observed airfare movement in date and
> route/airport/airline overlap; they are not confirmed causes."

Frontend copy follows the same rule (`NewsContextSection.tsx`,
`RiskGeographySection.tsx`): every EONET card includes the line
*"Potential contextual factor -- not a confirmed cause of this route's
fare movement,"* and weather conditions are shown with *"shown for
context only -- not a claim about what conditions were during the fare
movement."* No numeric adjustment, weighting, or exclusion of any fare
observation is ever made on the basis of an EONET event or weather
reading — see §7 for how this is structurally enforced, not just
promised in prose.

## 7. Failure isolation

Neither EONET nor OpenWeatherMap can ever break the index, analytics, or
the rest of the dashboard:

- **`EonetClient`/`OpenWeatherClient`** never raise across their own
  boundary — a network failure, timeout, malformed response, or (for
  OpenWeatherMap) a missing/invalid key degrades to a typed result
  (`EonetFetchResult`/`WeatherFetchResult`) with a non-`SUCCESS` status,
  exactly like this project's other real HTTP integrations
  (`scraper.models.SourceCallResult`, `newsdata_news_provider.py`).
- **`EonetContextService.get_context`/`WeatherContextService.get_route_weather`**
  additionally never raise even if something inside them does (both are
  wrapped in a defensive `try/except`), degrading to `status =
  "UNAVAILABLE"`.
- **`real_adapters.RealNewsContextEngine.get_route_context`** wraps both
  calls in a *second*, deliberate layer of `try/except` at the actual
  dashboard-facing seam.
- The frontend renders `"Event context unavailable right now"` /
  `weather_status !== "UNAVAILABLE"` gates rather than assuming success —
  see `NewsContextSection.tsx`.
- **Proven, not just asserted:** `tests/test_eonet_context.py`'s
  `test_index_value_identical_with_eonet_available_vs_unavailable`
  computes the same index from the same observations three times — once
  before any EONET call, once with EONET simulated up, once with EONET
  simulated down — and asserts the resulting `national_index` is
  identical in all three. The same test file's
  `test_index_engine_modules_never_import_eonet` inspects `index.py`'s
  and `aggregation.py`'s own AST to prove neither module imports
  anything EONET-related, structurally, not by convention alone.

**No mock EONET/weather content exists** (unlike News's
`MockNewsProvider`) — instead, when `NEWS_PROVIDER=mock` (the test
suite's default, `tests/conftest.py`), both services are wired to an
in-process offline stub (`real_adapters._OfflineHttpClient`) that fails
every call immediately with zero real socket activity, so `GET
/routes/{route}/context` never makes a live network call from an
automated test — same discipline the project already applies to keep
GDELT out of the test suite.

## 8. Weather (OpenWeatherMap)

A second, simpler context source: **current conditions** at a route's
two airports, via OpenWeatherMap's Current Weather Data API
(`GET /data/2.5/weather`). Unlike EONET, this genuinely requires a
credential (`OPENWEATHER_API_KEY`, read from the environment only,
never hard-coded/logged/returned).

Weather is a **live snapshot**, not a scored/ranked history — there is
no relevance function, no radius, no time window. Each airport's
conditions are fetched independently (`weather_context.WeatherContextService`)
and can independently succeed or fail — `RouteWeatherContext.status` is
`"OK"` (both sides succeeded), `"PARTIAL"` (one side succeeded), or
`"UNAVAILABLE"` (neither did, e.g. the key is unset or an airport has
no known coordinates). Results are cached in-process for 10 minutes per
coordinate pair to avoid re-fetching the same airport repeatedly.

**Verification caveat, stated plainly:** unlike every other real
integration added this session (SerpApi, newsdata.io, NewsAPI.org,
Event Registry, EONET — each verified against a real live response
before being written), `openweather_client.py` was built against
OpenWeatherMap's long-stable, extensively documented public contract
*without* a successful live call at authoring time: the provided key
returned HTTP 401, consistent with OpenWeatherMap's own documented
new-key activation delay (their FAQ states new keys can take up to ~2
hours), not necessarily an invalid key. **This was subsequently
verified live** once the key activated — a real call against
`GET /api/v1/routes/BLR-DEL/context` returned genuine current
conditions for both Bengaluru (29.3°C, overcast clouds) and Delhi
(29.0°C, light rain, 100% humidity), confirming the response parsing
was correct on the first real call.

## 9. Backend API

Both layers surface through the **existing** endpoints rather than
new, redundant ones, per this project's stated preference:

- **`GET /api/v1/routes/{route}/context`** (`api/routes/news.py`,
  unchanged path) — `RouteContextResponse` gained four new optional
  fields: `natural_events` (list), `natural_events_status`,
  `weather_origin`/`weather_destination`, `weather_status`. The
  existing `events`/`data_source` fields (news) are untouched.
- **`GET /api/v1/analytics/events`** (new, `api/routes/analytics.py`) —
  the one genuinely new endpoint, following the exact sibling pattern
  of `/analytics/data-quality` and `/analytics/forecast`
  (`analytics_service.get_natural_events`). Returns a **compact**
  national list: only EONET events associated with a route whose fare
  movement is *significant* (same `is_significant_movement` threshold
  the news layer already uses, reused not duplicated), capped at the
  top 10 by relevance — deliberately not "every EONET event near
  India," which would overwhelm a national view.

The frontend never calls EONET or OpenWeatherMap directly — every
request goes through this backend, so no secret is ever reachable from
browser code (see §10).

## 10. Security / environment-variable handling

- `EONET_API_KEY`, `EONET_BASE_URL`, `OPENWEATHER_API_KEY`,
  `OPENWEATHER_BASE_URL` are read from the environment only
  (`os.environ.get`), in `eonet_client.py`/`openweather_client.py`'s
  constructors — never hard-coded, never a default value baked into
  source, never printed, logged, or included in any exception message
  or returned value.
- Neither key is ever sent to, or reachable from, the frontend — see
  §9. Vite env vars (`VITE_*`) are never used for either.
- `.env.example` carries placeholders only (`EONET_API_KEY=`,
  `OPENWEATHER_API_KEY=`) — no real value.
- **Tested, not just asserted:** every client/context test file
  includes an explicit "key never leaks" test —
  `test_eonet_client.py::test_configured_api_key_is_included_but_never_returned`,
  `test_eonet_context.py::test_api_key_never_appears_in_context_result`
  (and the failure-path variant), `test_openweather_client.py::test_key_never_appears_in_returned_data`,
  `test_weather_context.py::test_api_key_never_appears_in_route_weather_result`.

## 11. Rate limits / known limitations

- **EONET**: no documented hard rate limit for the public REST API at
  the time of writing, but `EonetClient` caches in-process for 15
  minutes per unique query anyway, to avoid needless repeated fetches.
- **OpenWeatherMap**: free tier is limited (60 calls/minute, 1,000,000
  calls/month per OpenWeatherMap's published free-tier terms);
  `OpenWeatherClient` caches in-process for 10 minutes per coordinate
  pair.
- **In-process cache only** — not persisted, not shared across server
  restarts or multiple server processes (unlike the Postgres-backed
  `news_article_cache`). Acceptable for a single-process prototype;
  documented here as a real limitation, not silently glossed over.
- **Polygon-geometry events excluded from matching** — see §4. This
  measurably reduces coverage for `floods` specifically, since several
  observed flood events use Polygon geometry; any such event with a
  verified-safe `Point` entry is still used.
- **OpenWeatherMap response shape not independently verified against a
  live call at authoring time** — see §8's caveat, since resolved (a
  real live call has since confirmed correct parsing) but noted here
  for the record.

## 12. Index vs. context — the standing distinction

Same as `docs/news_context.md` already establishes for news, restated
here because it applies identically to EONET and weather:

**INDEX** = a statistical measurement (`AirfarePriceIndex`, DGCA
weighting, Data Quality validation) — real fare observations, real
statistics, never touched by anything in this document.

**EVENT CONTEXT** (news, EONET, weather) = explanatory information
shown *alongside* the index, answering "what might help explain this,"
never "why this happened" and never fed back into any number the index
engine produces.
