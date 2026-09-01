# Airfare Data Collection (Scraper)

**Status: SIH prototype.** This document describes the `scraper` package
— the layer that sits *before* `data_quality`, whose job is collection
only. It answers: "where does a fare observation come from before
`data_quality.validate_fare_batch` ever sees it?"

---

## 1. Division of labour

```
Airline / OTA / API sources
  -> scraper                (this package — COLLECTION only)
  -> raw fare observations  (docs/data_contract.md shape)
  -> data_quality            (VALIDATION — unchanged, see docs/data_quality.md)
  -> index_engine             (STATISTICS — frozen, unchanged)
  -> analytics / dashboard
```

The scraper never validates, cleans, deduplicates, or scores anything.
Those rules already exist in `data_quality` (and, as a second
independent pass, in `index_engine.validation`/`cleaning`) — duplicating
them here would mean two places could disagree about what "valid" means.
Concretely:

- The scraper assigns **deterministic, source-qualified observation IDs**
  so the same real quote seen twice is recognisable, but it never removes
  a suspected duplicate itself — `data_quality.duplicates` does that.
- The scraper never averages multiple sources' fares for the same route/
  date into one number — `index_engine`'s representative-fare statistics
  (median/mean/trimmed-mean) are what "one number per route/period" comes
  from, and they need every individual observation to work correctly.
- A record failing a scraper-side sanity check is still *returned*, not
  silently dropped — the scraper is not the authority on what's invalid.

## 2. Source evaluation

Item 4 of the brief: inspect which sources are actually accessible before
building anything, and never bypass a block. Six sources were evaluated —
a representative sample (official airline sites, OTAs, and third-party
flight-data APIs), not an exhaustive survey of every Indian carrier/OTA.
Full detail (domain, access method, robots.txt status, rate limits,
fields, limitations) lives in `scraper.live_sources.EVALUATED_SOURCES` as
structured data, not just prose, so a teammate can query it programmatically.

| Source | Category | Status | Why |
|---|---|---|---|
| IndiGo (goindigo.in) | Official airline site | `SOURCE_UNAVAILABLE` | **Updated finding:** IndiGo runs a real developer/NDC API program — the strongest airline-specific candidate. `scraper.indigo_source.IndiGoSource` is a credential-driven scaffold ready to receive real access, but production approval and a verified request/response contract are not yet in place. See §2a. |
| Air India (airindia.com) | Official airline site | `SOURCE_UNAVAILABLE` | Not independently re-tested this session (same category as IndiGo's old assessment); no confirmed public fare API |
| MakeMyTrip (makemytrip.com) | OTA | `SOURCE_UNAVAILABLE` | robots.txt fetch **timed out**; ToS prohibits automated scraping; `myPartner` is a B2B/travel-agent platform, not a public self-service fare API — do not reverse-engineer internal endpoints |
| Cleartrip (cleartrip.com) | OTA | `SOURCE_UNAVAILABLE` | Not independently re-tested this session. Earlier project notes referencing a possible public Cleartrip fare API/endpoints were **never verified** and must not be treated as fact or built against |
| Amadeus Self-Service Flight Offers Search API | Third-party API | `SOURCE_UNAVAILABLE` | **Updated finding: the self-service registration portal has since been shut down.** No longer a near-term path to credentials — do not build around it |
| Duffel API | Third-party API | `SOURCE_UNAVAILABLE` | Legitimate developer API with a real sandbox (fictional test airline — never present sandbox results as real Indian fares). No credentials configured; Indian domestic coverage in production unconfirmed |
| Travelpayouts / Aviasales | Third-party API | `SOURCE_UNAVAILABLE` | Possible source; likely cached/aggregated rather than live-quote data (unconfirmed). No credentials configured; Indian coverage unconfirmed |
| Aviationstack API | Third-party API | `SOURCE_UNAVAILABLE` | Requires a key nobody has configured, **and** doesn't return fare/price data at all (flight status/schedule only) — wrong data type regardless of credentials |

### 2a. IndiGo adapter scaffold

`scraper.indigo_source.IndiGoSource` reads credentials from environment
variables (`INDIGO_API_KEY`, optionally `INDIGO_USERNAME`,
`INDIGO_PASSWORD`, `INDIGO_API_BASE_URL` — see `.env.example`). Today it
always returns `SOURCE_UNAVAILABLE`, for one of two honestly-distinguished
reasons:

- No credentials configured (`error_detail` names the missing env var).
- Credentials configured, but `IndiGoSource._call_api` is intentionally
  a `NotImplementedError` — no real endpoint, auth flow, or response
  schema has been fabricated. See that method's docstring for exactly
  what's needed to complete it once real, verified IndiGo API access
  exists.

`LIVE_SOURCES` uses `IndiGoSource` (not the generic `UnavailableLiveSource`
wrapper) for IndiGo specifically, so this real credential-gated logic is
what actually runs in `mode="live"`.

**Honest limitation on the evaluation itself:** only IndiGo's and
MakeMyTrip's `robots.txt` were actually fetched this session (both timed
out — itself informative, matching the pattern of bot-protected consumer
travel sites). Air India and Cleartrip were categorized from the same
well-established pattern (official airline / OTA sites in this market
standardly run bot protection and prohibit automated scraping in their
ToS) rather than independently re-tested — flagged as
`empirically_tested_this_session=False` on their `SourceProfile` so this
is traceable, not asserted as fact.

**The honest bottom line:** given this project's constraints (no
credentials provided, no bypassing bot protection/CAPTCHAs/ToS), **zero
sources can currently be live-scraped legitimately.** That is not a gap in
the scraper's architecture — `scraper.source.FareSource` and
`scraper.runner` are fully built and tested against mock data — it is a
fact about the current state of credentials and access. The Amadeus API
is the strongest candidate for the *first* real source, purely because
it's a legitimate, documented, fare-relevant API — someone just needs to
register for it and hand this project the resulting key.

### Adding a real source later

1. Register for/obtain legitimate credentials (e.g. Amadeus).
2. Add a `SourceProfile` to `scraper.live_sources.EVALUATED_SOURCES` (or
   update the existing one) documenting the real access details.
3. Write a new `FareSource` subclass (see `scraper.source.FareSource`)
   that calls the real API/site through the request lifecycle already
   built (`scraper.rate_limit.RateLimiter` +
   `scraper.rate_limit.retry_with_backoff`) and maps results to
   `RawFareObservation`.
4. Nothing else changes — `scraper.runner.run_scrape` only ever talks to
   the `FareSource` interface.

## 3. Mock vs live mode

`ScraperConfig(mode="mock")` (the default) uses
`scraper.mock_source.MockFareSource` — three simulated sources
(`MockIndiGo`, `MockAirIndia`, `MockOTA_ClearSky`) producing
**deterministic**, clearly-labelled (`is_mock=True`) fabricated fares. Same
route + date + source always produces the same fare (a SHA-256 hash of
those inputs, not a global random seed), so a demo run is reproducible
without any shared mutable random state leaking between calls.

`ScraperConfig(mode="live")` uses `scraper.live_sources.LIVE_SOURCES` —
see §2: every entry currently returns a structured `SOURCE_UNAVAILABLE`
result, never a fabricated fare. **A live-mode run today collects zero
observations and a run report full of honest, documented failures — that
is the correct behaviour**, not a bug, until a real source is connected.

Nothing downstream can confuse the two: every mock observation carries
`is_mock=True`; a real observation from a future live source must set
`is_mock=False`. `examples/scraper_demo.py` refuses to describe output as
"real" unless every observation in the batch has `is_mock=False`.

## 4. Route input

`scraper.routes.load_routes(tiers=(1,))` reads
`data/routes/recommended_routes.json` — the route list is never
hard-coded in this package. Tier 1 = top 20 routes by national traffic
weight (the DGCA-derived ranking, see `data/traffic/README.md`), Tier 2 =
next 30 (ranks 21–50), Tier 3 = next 50 (ranks 51–100).
`ScraperConfig.tiers` defaults to `(1,)` so a first run stays small.

Of the file's 100 rows, 12 have a deliberately null
`origin_iata`/`destination_iata` (`city_mapping.py`'s documented
"MUMBAI (MUMBAI)"/"MUMBAI (NAVI MUMBAI)" exclusions, kept separate from
the real MUMBAI/BOM entry to avoid double-counting — all 12 also carry
`currently_covered: false`). `load_routes()` skips these: a source can
never be sensibly asked to search a route with no IATA code, so the
scraper never generates a `SearchRequest` for one. This is why
`load_routes(tiers=(1,))` returns 18 routes, not 20 — see
`tests/test_scraper_routes.py::test_routes_with_no_iata_mapping_are_never_returned`.

## 5. Booking-horizon sampling

`scraper.runner.generate_booking_horizon_dates(today)` samples one
representative flight date inside each bucket of
`index_engine.config.BOOKING_HORIZON_BUCKETS` — it imports that tuple
rather than redefining the horizon boundaries, so if the engine's buckets
ever change, the scraper's sampling follows automatically. `booking_date`
is always `today`; `booking_horizon_days` is always derived as
`(flight_date - booking_date).days` (see `SearchRequest.booking_horizon_days`),
never requested from a source.

## 6. Provenance and observation IDs

Every observation carries `source`, `source_url` (`None` for mock data —
there is no real page to link to), `scraped_at`, and `run_id`. These are
extra columns beyond `docs/data_contract.md`'s required+optional set;
both `index_engine.validation.validate_observations` and
`data_quality.validation.check_schema` only check that the *required*
columns are present and never reject on unrecognised extra columns, so
this is safe.

`observation_id` is a deterministic hash of
`(source, origin, destination, flight_date, booking_date, fare_class)` —
stable across repeated calls with the same inputs, and namespaced by
source so IndiGo's and an OTA's quotes for the same route/date can never
collide into one ID. It deliberately does **not** include `run_id`, so the
same real-world quote seen again in a later run is still recognisable —
`data_quality.duplicates` is what decides what to do about that
recognition, not this package.

## 7. Raw vs validated storage

```
data/
├── raw/fares/<run_id>.jsonl          scraper.storage.write_raw_run(...)
├── validated/fares/<run_id>.jsonl    scraper.storage.write_validated_run(...)
└── scraper_runs/<run_id>.json        scraper.storage.write_run_report(...)
```

Physically separate trees, not a flag column, so a consumer can never
accidentally point the index engine at the raw tree. Every write is
exclusive-create (`open(path, "x")`) — writing the same `run_id` twice
raises `FileExistsError` rather than silently overwriting a previous run.

## 7a. JSON collection envelope (primary team handoff format)

`scraper.storage.write_collection_json(report, observations, route_attempts=None, base_dir="data")`
writes the single-file JSON handoff the rest of the team consumes:

```
data/collections/<run_id>.json
{
  "schema_version": "1.0",
  "collection_metadata": { ... ScrapeRunReport.to_dict() ... },
  "route_attempts": [ ... report.to_route_attempts() by default ... ],
  "observations": [ ... one object per individual fare quote, never aggregated ... ]
}
```

This is additive to, not a replacement for, the raw/validated `.jsonl`
trees in §7 — those remain the internal raw-vs-validated audit trail;
this envelope is the one file to actually hand to another teammate or
load with `scraper.storage.load_json_observations(path)`, which returns
`payload["observations"]` directly, ready to pass as
`data_quality.validate_fare_batch(raw_data=...)`. Exclusive-create, same
as every other writer here — a duplicate `run_id` raises
`FileExistsError` rather than overwriting a previous run.

`examples/scraper_demo.py` writes this envelope on every run (mock or
live) right after `run_scrape(...)` returns, including the honest
zero-observations case in live mode today.

## 7b. Credential handling

No real credentials exist in this repository, in tests, or in any
committed file — `.gitignore` excludes `.env*` (except `.env.example`,
which contains only empty placeholders). To use a real source adapter
locally: copy `.env.example` to `.env`, fill in real values, and load
them into your shell/process before running the scraper (e.g. via
`python-dotenv` or your shell's own env-var mechanism — this project does
not currently auto-load `.env`, to avoid an extra dependency for a
prototype with zero connected real sources today).

## 8. Scraper health / run report

`ScrapeRunReport` (see `scraper.models`) tracks, per source: routes
requested/successful/failed, routes attempted, observations collected,
and a failure-reason breakdown (`TIMEOUT`, `HTTP_ERROR`, `RATE_LIMITED`,
`PARSE_ERROR`, `MALFORMED_RESPONSE`, `EMPTY_RESULT`,
`SOURCE_UNAVAILABLE`). Nothing is hidden — a failed route/source shows up
in the report, never just silently missing.

`report.to_route_attempts()` is shaped exactly as
`data_quality.health` documents its `route_attempts` input — pass it
straight into `validate_fare_batch(raw_data, route_attempts=...)` to get
`routes_requested`/`routes_successful`/route-coverage metrics on the
`data_quality` side too, rather than the scraper maintaining a second,
possibly-inconsistent health report.

## 9. Retries, rate limiting, concurrency

`scraper.rate_limit.RateLimiter` enforces a minimum interval (default 1s)
between two requests to the *same* source, plus optional random jitter —
including between retries of the same request, not just the first attempt.
`scraper.rate_limit.retry_with_backoff` retries with exponential backoff
(default base 1s, capped at 20s), up to `ScraperConfig.max_retries`
(default 3) — conservative defaults, not an aggressive crawler.
`scraper.runner._call_source` retries both a raised exception (a genuine
programming/connection error) *and* a normally-returned
`SourceCallResult` whose status is `TIMEOUT`, `HTTP_ERROR`, or
`RATE_LIMITED` — the three transient conditions worth asking again for.
It never retries `EMPTY_RESULT` (the source answered normally and just
had nothing), `SOURCE_UNAVAILABLE` (a deliberate, permanent "don't access
this" marker — retrying would mean hammering a source already decided
against), or `PARSE_ERROR`/`MALFORMED_RESPONSE` (more likely a bug in our
own parsing than a transient server issue). `scraper.runner.run_scrape` uses a bounded
`ThreadPoolExecutor` (`ScraperConfig.max_concurrency`, default 4) across
all route/date/source combinations, so throughput scales with route count
without becoming unbounded concurrent load on any one source (the
per-source `RateLimiter` still throttles each source independently of how
many workers are running).

## 10. Historical data — an explicit limitation

This scraper only ever collects **current, forward-looking fare quotes**
(a real-time "what does this flight cost right now" query) — it cannot
retroactively obtain what a route cost last month. There is no permitted
source of historical per-fare pricing available to this project. Building
a real booking-horizon/monthly time series therefore requires running
this scraper repeatedly over time (see §11) and accumulating real
observations going forward — it cannot be backfilled.

## 11. Scheduling

Not implemented as an actual cron/scheduler in this prototype — `run_scrape`
is a plain function a caller invokes (manually, or from whatever job
runner the deployment uses). The intended cadence: once daily, sampling
the booking-horizon dates in §5 relative to that day, so the dataset's
booking-horizon coverage builds up gradually and honestly over real
calendar time, exactly as item 19 of the brief describes.

## 12. Reproducibility

- Mock fares are a deterministic hash of inputs, not `random.seed(...)` —
  no shared global random state to accidentally perturb between calls or
  test files (see §3).
- `generate_booking_horizon_dates` is a pure function of `today` and the
  engine's own bucket config — no hidden current-date dependence beyond
  the explicit `today` parameter.
- Tests never depend on a live network call (see `tests/test_scraper_*`) —
  every test uses `MockFareSource`, hand-built `FareSource` fakes, or the
  documented-unavailable `UnavailableLiveSource`.

## 13. Known limitations

- **Zero real sources connected today** — see §2. This is the single
  biggest gap before this project's index reflects real airfares rather
  than synthetic data (see `examples/generate_sample_fares.py`'s own
  "SYNTHETIC DEMONSTRATION DATA" disclaimer).
- **No currency conversion** — inherited from `docs/data_contract.md`;
  the scraper always sets `currency="INR"` for mock data and would need
  the same INR assumption from any real source, since nothing downstream
  converts currencies.
- **Concurrency is thread-based**, not async — fine at today's scale
  (100 routes x handful of sources), would need revisiting well before
  500+ routes x many sources x fine-grained booking-horizon sampling.
- **No persistent job scheduler** — see §11.
- **`Air India` and `Cleartrip` were not independently re-tested this
  session** — see §2's honesty note.
