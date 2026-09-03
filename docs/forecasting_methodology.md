# Forecasting Module — Methodology (Stage 1–3.1, CPI Benchmark)

**Status: SIH prototype, incremental build.** This document
describes the forecasting methodology implemented so far. Like
`docs/methodology.md`, it is written to be honest about what is real,
what is synthetic, and what is a genuine statistical claim versus an
illustrative one — nothing here should be presented to a judge or user as
more validated than it actually is.

This module does not compute, recompute, or duplicate anything
`index_engine` already computes. It consumes `index_engine`'s public
output (via `AirfareAnalytics`) and builds forecasting-specific data
preparation, baseline models, and backtesting on top of it.

---

## 1. What this stage covers

- **Stage 1**: a data-access/preparation layer (`forecasting.data_access`)
  that reshapes `index_engine`'s per-period output into forecasting-ready
  historical tables — national-level and route-level.
- **Stage 2**: exploration of the actual dataset produced by Stage 1 (no
  new code — see the project's Stage 2 report).
- **Stage 3**: national-level baseline forecasting and rolling-origin
  backtesting.
- **Stage 3.1**: real-data readiness fixes to Stage 3, found by an
  explicit audit before any real scraped data existed to break things
  silently. Every fix in §9–§12 addresses a specific audit finding.
- **CPI Benchmark** (this document's main new subject for this revision):
  a structural comparison pipeline against MoSPI's official CPI Airfare
  sub-index — see §16–§17.

Route-level forecasting, trend analysis, anomaly detection, booking-horizon
analytics, and alerts are **not yet built** — see the project's step-by-step
implementation plan for sequencing.

## 2. Target definition

The forecasting target is `national_index` — the national airfare price
index value computed by `index_engine.AirfarePriceIndex`, exactly as it
already exists (base period = 100). This module does not define a new
target or reinterpret the index in any way; it forecasts the same number
`index_engine` computes for historical periods.

Periods where `index_engine` could not compute `national_index` (value is
`None`) are represented as **`NaN` at their correct calendar position** in
the training series — never dropped, never filled, interpolated, or
guessed. See §9 for why preserving the calendar position (rather than
dropping the row) matters, and `forecasting.series.national_index_series`
for the implementation.

## 3. Time frequency

**Monthly.** `index_engine` periods every observation by `flight_date` (see
`normalization.add_period`), not `booking_date` — this module's period
derivation (`forecasting.data_access.derive_calendar_periods`) is
deliberately consistent with that, and this document reaffirms it: a
forecast for period `2026-09` predicts the index for flights departing in
September 2026, not fares booked in September 2026.

## 4. Forecast horizon

**One month ahead only, in this stage.** `forecast_national_index` raises
`ValueError` if called with `horizon != 1`. Multi-step forecasting is
explicitly out of scope until the single-step baselines here have been
validated against real (non-synthetic) data with enough history to
support it — extending the horizon on an 8-point synthetic series would
not produce a meaningfully validated result.

## 5. Baseline models

Three simple, fully explainable models, implemented in
`forecasting.baseline_models`. They exist to establish a statistically
defensible floor — any future, more complex model (ARIMA/ML/deep learning)
must be shown to outperform these before it is worth adopting.

| Model | Definition | Minimum data |
|---|---|---|
| `naive` | Forecast = most recent observed value | 1 point |
| `historical_mean` | Forecast = mean of all historical values | 1 point |
| `moving_average` | Forecast = mean of the last `window` values (default 3) | `window` points |

**Why not ARIMA/SARIMA/Prophet/ML/deep learning yet?** These models have
enough free parameters (or, for deep learning, orders of magnitude more)
that fitting them on an 8-point series would overfit trivially and
produce a confident-looking number with no real statistical support. A
seasonal model in particular needs multiple full yearly cycles to
distinguish real seasonality from noise (see §8) — this dataset has
about 0.67 of one year. Introducing these models now would produce
output that *looks* more sophisticated while being *less* trustworthy
than the baselines here. They remain the natural next step once enough
real historical data exists to fit and validate them properly.

## 6. Rolling-origin (walk-forward) backtesting

Implemented in `forecasting.backtesting.rolling_origin_backtest`. At each
split `k` (training window size), only periods `series.iloc[:k]` are
visible to the model; it is evaluated against period `k + horizon - 1`. No
future observation is ever used to produce a past forecast — verified
directly by tests that spy on every value a model is shown during
backtesting, including a version of that test with a calendar gap present.

```
train=[Jan]                 -> predict Feb
train=[Jan, Feb]            -> predict Mar
train=[Jan, Feb, Mar]       -> predict Apr
...
```

Two distinct "nothing to score" cases are reported separately, neither
counted as an error and neither silently absorbed into MAE/RMSE/MASE:

- **`MODEL_NOT_APPLICABLE`**: the target period is fine, but the model
  couldn't produce a forecast from the training window (e.g.
  `moving_average` with `window=3` hasn't yet seen 3 real calendar-adjacent
  points).
- **`TARGET_UNAVAILABLE`** (added in Stage 3.1): the target period itself
  has no trustworthy value to score against (missing, or filtered out by
  `min_coverage_rate` — see §12–13). No model is at fault here; there's
  simply no ground truth for that period.

## 7. Evaluation metrics

- **MAE** (Mean Absolute Error) and **RMSE** (Root Mean Squared Error):
  computed directly from backtest residuals across all successful folds.
- **MASE** (Mean Absolute Scaled Error): each fold's absolute error is
  scaled by that fold's own **in-sample** one-step naive MAE (the mean
  absolute difference between consecutive training-window values) — the
  standard Hyndman & Koehler definition. A fold whose training window has
  fewer than 2 points cannot supply this scale (no difference exists to
  compute) and is excluded from the MASE average specifically, while still
  contributing to MAE/RMSE if it produced a forecast. If **no** fold can
  supply a scale, `mase` is `None` and `mase_status` states why — never a
  fabricated placeholder value.
- **MAPE is deliberately not implemented** in this stage, per instruction
  not to rely on it as a primary metric; MAE/RMSE/MASE together give a
  fuller picture without MAPE's known distortions on small or near-zero
  bases.
- **Fold-count reliability**: when a model produces fewer than 3 backtest
  folds, `ModelEvaluationResult.notes` explicitly flags the metrics as
  illustrative rather than statistically reliable.

## 8. Confidence intervals

`ForecastResult.lower_bound`/`upper_bound` are only populated when at
least 3 backtest residuals exist. When available, the interval is a rough
empirical one: `forecast ± 1.96 × std(backtest residuals)` (a normal
approximation over a very small residual sample) — explicitly labeled in
`ForecastResult.notes` as illustrative, not a statistically rigorous
prediction interval. Below 3 residuals, both bounds are `None` and the
note explains why. No interval is ever fabricated from a formula without
empirical backing.

## 9. Calendar-gap handling (Stage 3.1 fix)

**The problem this fixes.** Earlier, `national_index_series()` dropped
every period with a `None` `national_index`, producing an array whose
*positions* no longer corresponded to real calendar months. Any
positional operation downstream — backtesting fold construction, MASE's
in-sample scale, `moving_average`'s window — could then silently treat two
calendar months separated by a real gap as if they were adjacent,
corrupting every metric with no warning.

**The fix.** `national_index_series()` now returns a series covering
**every period in `ForecastingDataset.periods`**, with `NaN` standing in
for a period with no trustworthy value — the same calendar-complete range
Stage 1 already builds, simply no longer discarded. Position `k` is now
guaranteed to be exactly one calendar month after position `k-1`.

**Backtesting is now calendar-correct as a result:**

- `rolling_origin_backtest` includes an explicit **contiguity guard** — for
  every fold, it asserts (using `index_engine.utils.shift_period`) that the
  target period is genuinely `horizon` calendar months after the training
  cutoff. With a calendar-complete series this always holds; if a caller
  ever passes in a series with rows actually removed for a gap, this
  raises `ValueError` immediately rather than silently mislabeling a fold.
- A fold whose **target** is `NaN` is skipped (`TARGET_UNAVAILABLE`) — no
  interpolation, no guess, not scored as an error.
- **`naive`/`historical_mean` skip past gaps** in their training window to
  find the most recent/all real values — this is *not* interpolation (no
  value is invented for the gap itself), just reuse of genuine past
  observations, which is the standard meaning of "persistence" in the
  presence of missing data.
- **`moving_average` does NOT skip gaps.** It requires the literal most
  recent `window` calendar slots to all be real; if even one is missing,
  it returns `None` (`MODEL_NOT_APPLICABLE`) rather than reaching further
  back to "find" enough real points elsewhere — doing so would silently
  redefine what "the last `window` months" means.
- `MASE`'s in-sample naive scale (`_one_step_naive_in_sample_mae`) is
  gap-safe by construction: `pandas.Series.diff()` produces `NaN` across a
  gap, and those are excluded — a difference spanning a gap is correctly
  never treated as a genuine one-step difference.

**Single live forecasts** (`forecast_national_index`) are now anchored to
the **last real (non-gap) period**, not the literal last calendar slot —
if the most recent month happens to be a gap itself (e.g. this month's
data hasn't fully arrived), the forecast still answers "one month past the
last thing we actually know," not "one month past a period we also have
no data for."

## 10. Optional data-quality filtering

`ForecastingDataset` already carries `coverage_rate` per national period
(the fraction of route weight for which `index_engine` had a usable
index that period). Stage 3 originally ignored this entirely — a period
computed from, say, 1 surviving route out of 10 was treated as equally
trustworthy as a fully healthy one.

`national_index_series()` (and therefore `forecast_national_index()` /
`evaluate_national_baselines()`) now accept an optional
`min_coverage_rate` parameter. **`None` (the default) applies no
additional filtering** — every period `index_engine` was willing to
compute a number for is used as-is. If set, any period below that
threshold is treated as `NaN` (missing) for forecasting purposes, exactly
like any other gap — same handling, same "never scored, never
interpolated" guarantees from §12. This is never applied silently:
passing a threshold is a deliberate choice that changes what the
training/backtesting sample considers trustworthy, and should be
documented whenever it's used in a report or demo.

## 11. Date sanity bounds

`derive_calendar_periods()` runs on **raw, unvalidated** observations —
before `index_engine.validation` ever sees them. A single malformed or
typo'd scraped date (a realistic scraping artifact — e.g. a stray "2099"
or "1900") could previously expand the derived period range to decades,
each spurious period then triggering an expensive
`AirfareAnalytics.calculate()` call.

Any `flight_date` value more than `max_past_years` years before, or more
than `max_future_days` days after, an explicit `reference_date` is now
excluded before the range is computed (defaults: 10 years past, 400 days
future — both configurable per call). Exclusions are never silent: a
`UserWarning` is raised via Python's standard `warnings` module, and when
`build_forecasting_dataset()` auto-derives periods (no explicit `periods`
argument), the same exclusion counts are also recorded in
`ForecastingDataset.warnings`.

`reference_date` must always be passed explicitly in tests — never
inferred from the real current date, which would make a test's pass/fail
status silently depend on when it happens to run.

## 12. Explicit period-list validation

When `periods` is supplied explicitly to `build_forecasting_dataset()`
(bypassing auto-derivation), it is now validated: **malformed** period
strings (anything that doesn't parse as `YYYY-MM`) and **duplicate**
periods are rejected outright with `ValueError` — both are genuinely
ambiguous inputs that can't be safely auto-corrected. **Out-of-order**
input is not rejected; it is silently sorted ascending instead, since
ordering is not load-bearing anywhere else in this module — every other
view onto a `ForecastingDataset` already re-sorts by period rather than
trusting input order, so rejecting a merely-unsorted list would be
inconsistent with the rest of the module's conventions for no real
benefit.

## 13. Limitations caused by the current 8-month synthetic dataset

- **Only 8 monthly observations exist** (`2026-01`–`2026-08`), all from
  `generate_sample_fares.py`'s fabricated random-walk-with-drift pattern
  (`random.seed(42)`) — not real Indian airfare behavior.
- **No year-over-year signal exists at all** (`yoy_change_pct` is `None`
  for every period, since there's no 2025 data) — nothing about yearly
  seasonality can be learned or claimed from this dataset.
- **At most 7 backtest folds are possible** for any one-step model, and
  fewer for models with a data requirement beyond 1 point (e.g.
  `moving_average` loses 2 folds to its window requirement) — too few for
  strong statistical confidence in any single metric value.
- **All 10 routes happen to have zero gaps** in this specific synthetic
  sample — a property of the generator, not something the forecasting
  code assumes; both the underlying data-access layer (Stage 1) and the
  backtesting/forecasting logic itself (Stage 3.1, §9) are built to
  handle real gaps (`NEW_ROUTE`/`DISCONTINUED`/missing periods, and
  national-level gaps) correctly regardless — this is now covered by
  dedicated regression tests using deliberately gap-containing series,
  not just inferred from the gap-free synthetic sample.
- Every `ForecastResult` carries `is_synthetic_data=True` against this
  dataset specifically so downstream consumers (dashboard, reports) are
  never able to silently present these numbers as real predictions.

**These limitations are unchanged by Stage 3.1.** Stage 3.1 did not add
data, and does not claim to — it fixed how the *existing* 8-point dataset
(and any future longer one) is handled, so that when real, longer, and
possibly gap-containing data does arrive, the pipeline doesn't silently
mishandle it. All of the above remains true of the current dataset today.

## 14. Prototype validation vs. real-world forecasting — explicit distinction

**What has been validated:** the backtesting *mechanics* — no data leakage
occurs, MAE/RMSE/MASE are computed correctly against hand-checked manual
examples, skipped folds are correctly excluded from metrics rather than
scored as errors, and the code correctly reports when a metric cannot be
computed rather than guessing.

**What has NOT been validated:** whether any of these baseline models
would perform well on real Indian airfare data. The backtest results in
this stage measure only how well `naive`/`historical_mean`/`moving_average`
happen to fit an 8-point synthetic series generated by
`random.seed(42)`. A low MAE here is not evidence of real-world forecast
accuracy — it is only evidence that the code correctly measured fit
against fabricated numbers. This distinction must be preserved in any
report, presentation, or judge Q&A: this stage validates the **pipeline**,
not a **real-world prediction capability**.

## 15. Readiness for real, longer historical data

The code makes no assumption specific to 8 points or to this dataset:
`rolling_origin_backtest`, `forecast_national_index`, and
`evaluate_national_baselines` all operate on whatever length of series
`national_index_series` produces. Once real scraped fare data accumulates
(ideally 24+ months, to support real seasonal analysis later), the same
functions will run unchanged against a longer, real series — only the
`is_synthetic_data` flag and the interpretation of the results should
change, not the code itself.

## 16. CPI Benchmark: comparing our national index to MoSPI's official CPI

`forecasting.cpi_loader` / `forecasting.cpi_results` /
`forecasting.cpi_benchmark` compare our computed national index against
the Ministry of Statistics and Programme Implementation's (MoSPI) official
Consumer Price Index sub-index for domestic air travel.

**What the MoSPI series represents.** `data/benchmarks/cpi_1337.xlsx` is
MoSPI's published CPI sub-index for **Airfare**, under Transport →
Passenger transport services → Passenger transport by air → domestic,
scoped to **All India, Combined** (rural+urban) sector, series "Current".
This is an official, household-expenditure-weighted, nationally
representative statistic — collected and compiled by MoSPI through its own
methodology, entirely independent of this project's DGCA-traffic-weighted,
scraped-fare index. MoSPI's index is pinned to a **base year of 2024
(annual average = 100)** — a fixed field in the extract (`base_year`),
distinct from and unrelated to whatever `base_period` this project's own
`AirfarePriceIndex` happens to be configured with.

**Why raw levels can't be compared directly.** Our index and MoSPI's index
sit on different bases (an arbitrary `base_period` we choose, e.g.
`"2026-01"`, versus MoSPI's CY2024 average) and reflect different
methodologies and sampling. An index value of 110 on one series and 125 on
the other says nothing about relative price level on its own. Comparing
raw levels would be statistically meaningless.

**Rebasing.** Before any comparison, both series are rebased to 100 at the
**first period where both series have a trustworthy value** (the overlap
window's start) — `rebased = 100 × value / value_at_overlap_start`, applied
independently to each series. This is the standard technique for putting
two differently-based indices on a common footing for level comparison.
Growth-rate metrics (month-over-month % change, correlation) are
unaffected by the rebasing choice, since they're computed from ratios of
consecutive values either way.

**Comparison metrics.**
- **Rebased levels**, per overlapping period — for visual/tabular
  comparison.
- **Month-over-month (MoM) % change**, computed only between two overlap
  periods that are genuinely **calendar-adjacent** (verified via
  `index_engine.utils.shift_period`, the same discipline established in
  §9) — never bridging a gap.
- **Mean absolute MoM difference**, requiring at least **2 valid MoM
  pairs** (i.e. at least 3 consecutive overlapping levels) before it is
  reported; `None` with an explanation below that.
- **MoM correlation (Pearson)**, requiring at least **4 valid MoM pairs**
  before it is reported at all — and even then, every result explicitly
  labels it "illustrative only, not a statistically reliable measure of
  relationship" given how few points are realistically available.
- **Year-over-year (YoY) comparison**: implemented (Stage 4) — see §21
  for the full methodology. In short: a period gets a YoY value only
  when the period exactly 12 calendar months prior is also in the
  our/MoSPI overlap and trustworthy on both sides; otherwise it is
  excluded, never fabricated.

**Missing periods.** A period missing on either side (no trustworthy value
on our side, or absent from MoSPI's extract) is excluded from that
period's comparison entirely — never interpolated, never filled. This is
the same "NaN means missing, never guessed" principle as §9, applied here
to a second data source.

**MoSPI's imputation flag, kept separate from our own quality signals.**
`cpi_1337.xlsx`'s `imputation` column (all `"N"` in the current extract —
i.e. nothing was imputed) is surfaced per-period as `mospi_imputed` on
each comparison row, and — by default (`exclude_mospi_imputed=True`) — an
imputed MoSPI period is excluded from MoM/correlation metrics (its rebased
level is still shown, for transparency). This is a completely separate
mechanism from our own `min_coverage_rate` filtering (§10): one describes
whether *MoSPI's own value* for a period is an original observation, the
other describes whether *our own computed index* for a period is
trustworthy. The two are never merged into a single blended quality score
— consistent with this project's broader convention of keeping distinct
quality signals distinct (see also how `data_quality`'s `SUSPICIOUS_FARE`
flag is kept separate from `index_engine`'s own statistical outlier
detection).

## 17. CPI Benchmark limitations — synthetic-data honesty

**This is a structural comparison pipeline, not a validation exercise, for
as long as the underlying fare data is synthetic.** Every
`CPIBenchmarkResult` built from `sample_fares.csv` carries
`is_synthetic_airfare_data=True` (a required parameter with no default —
the same explicit-over-implicit convention now applied to
`rolling_origin_backtest`/`forecast_national_index`/
`evaluate_national_baselines`'s `is_synthetic_data` parameter, so a real-
data caller is always forced to consciously state which kind of data
they're using rather than inheriting a default), and every successful
comparison's `notes` field restates this explicitly.

With the current 8-month synthetic sample (`random.seed(42)`, no real
airfare behavior):
- The real overlap with MoSPI's extract is only **7 months** (Jan–Jul
  2026) — too short for statistical confidence in a correlation or
  mean-difference metric regardless of whether the underlying data is
  real or synthetic.
- Any computed MoM difference or correlation describes how a **fabricated**
  series happens to move relative to MoSPI's real CPI — it is not
  evidence of real-world tracking accuracy in either direction. A small
  difference today is coincidence, not validation; a large difference is
  not evidence of a flaw.
- **YoY comparison against the real `sample_fares.csv`/`cpi_1337.xlsx`
  overlap is `INSUFFICIENT_DATA`** — not because YoY logic is missing
  (it's implemented, see §21), but because our current airfare history
  provides no prior-year signal at all (only Jan–Aug 2026, no 2025 data).
  The mechanism is real and tested against synthetic multi-year
  fixtures (§21); what's still missing is 12+ months of real airfare
  history to exercise it on real data.
- Even with real, longer airfare data, a difference from MoSPI would
  **not automatically indicate an error** in either series — the two
  measure different things (traffic-weighted ~10-route scraped median vs.
  official expenditure-weighted national collection) and are expected to
  diverge for legitimate methodological reasons, not just measurement
  error. This must be stated alongside any reported comparison number in
  a report or demo, not left implicit.

## 18. Scraper output ingest

`ingest.py` is a thin adapter between the scraper package's on-disk
output (`data/raw/fares/<run_id>.jsonl` / `data/validated/fares/<run_id>.jsonl`,
one JSON object per line, matching `RawFareObservation.to_record()`) and
`build_forecasting_dataset()`. Its only job is removing the manual step
of turning scraper JSONL files into the `observations` argument that
function already accepts — it introduces no new index, aggregation, or
data-quality business-rule logic.

**What it filters, and what it deliberately does not.** Before handing
records to `build_forecasting_dataset()`, `build_dataset_from_scraper_output()`
drops rows missing any of the 8 required data-contract fields, or with a
non-positive/non-numeric `total_fare` — the same fields index_engine's
own required-columns check demands, so this is schema-presence checking,
not a reimplementation of data_quality's business rules (suspicious-fare
thresholds, duplicate detection, staleness, source/route health all
remain entirely out of scope here). If pointed at a `data/validated/fares/`
file (already VALID+FLAGGED only, post data_quality — see the scraper
package's `storage.py`), this filtering is a no-op safety net. If pointed
at `data/raw/fares/` instead, unvalidated-but-structurally-intact rows
pass straight through unfiltered by any business rule.

**Real vs. synthetic data.** Every `RawFareObservation` carries an
`is_mock` field. `ScraperIngestResult` reports `real_record_count`,
`synthetic_record_count`, `is_synthetic_data` (True only if every usable
record is synthetic), and `is_mixed_data` (True if both are present).
Mixed input raises `ValueError` unless `allow_mock=True` is passed
explicitly — this adapter never silently blends real and synthetic
observations into one dataset. `is_synthetic_data` from the result should
always be passed straight through to `forecast_national_index()` /
`evaluate_national_baselines()`'s own required `is_synthetic_data`
parameter (§ CPI Benchmark's synthetic-data-honesty convention, applied
here too) — never hard-coded.

**What is preserved unchanged.** Calendar-gap handling (§9), contiguity
guards, date-sanity bounds (§11), and explicit period-list validation
(§12) are all enforced by `build_forecasting_dataset()` itself, called
here unmodified — this adapter neither bypasses nor duplicates any of
that behavior.

## 19. Route-level baseline forecasting

`route.py` extends Stage 3/3.1's national-level baseline forecasting to
individual routes, reusing the exact same architecture rather than
introducing a parallel one. `forecast_route_index()` /
`evaluate_route_baselines()` mirror `forecast_national_index()` /
`evaluate_national_baselines()` field for field: same
`is_synthetic_data`-required convention, same `horizon == 1` restriction,
same backtest-derived (never formula-fabricated) prediction interval, same
`ForecastResult` / `ModelEvaluationResult` types. No model, backtesting,
or index/aggregation logic is duplicated — both functions call the same
generic `forecasting.baseline_models.BASELINE_MODELS` and
`forecasting.backtesting.rolling_origin_backtest` national-level
forecasting already uses, fed a route's series instead of the national
one.

**`route_index_series()`.** The per-route counterpart to
`national_index_series()` (§9): a calendar-complete `pandas.Series` of one
route's `route_index` values, `NaN` for any period without a trustworthy
value — including any period where index_engine classified the route as
something other than OK (`NEW_ROUTE` / `DISCONTINUED` /
`INSUFFICIENT_DATA` / `NO_BASE_DATA`; see `ForecastingDataset`'s
docstring). There is no `min_coverage_rate` parameter here:
`coverage_rate` is a national-level concept (fraction of *routes* covered
in a period) with no equivalent column on `ROUTE_COLUMNS` — a route's own
status is already index_engine's quality signal for that route/period,
and `route_index` is already `None` whenever status isn't OK. An unknown
route name raises `ValueError` rather than silently returning an
indistinguishable all-`NaN` series — a typo is a caller error, not a
route with a real, total data gap.

**Insufficient history, per route, without crashing other routes.** A
route with zero OK periods produces `STATUS_INSUFFICIENT_DATA` from
`forecast_route_index()` / `evaluate_route_baselines()` — the exact same
status national-level forecasting already reports for a too-thin history,
reused rather than introducing a new status. `forecast_all_routes()` /
`evaluate_all_routes()` run the single-route functions across every route
in `dataset.route_list()`, and each route's result is fully independent:
one route's insufficient data produces an `INSUFFICIENT_DATA` entry for
*that route only*, and never prevents another route's `OK` result from
being produced (see `tests/test_route_forecasting.py`'s multi-route
independence tests).

**What is preserved unchanged.** Calendar-gap handling, the contiguity
guard in `rolling_origin_backtest()`, and the leak-free walk-forward
backtest split are all identical to the national-level path — this stage
adds no new gap-handling or leakage-prevention logic, it reuses what §9
and `backtesting.py` already enforce, per route.

**Scope note.** As at the national level, only `horizon == 1` and the
three existing baseline models (naive, historical mean, moving average)
are supported per route — multi-step horizons and non-baseline models
remain out of scope until real, longer route-level history exists to
validate them against (§13, §15).

## 20. Booking-horizon analytics

**Contract check, done before writing any code, not assumed.**
`RawFareObservation` has no `advance_purchase_days` field. It does have
`flight_date` and `booking_date` as two of its 8 *required*
(non-`Optional`) fields — confirmed by reading the dataclass directly,
not inferred. Every scraper source that can ever actually return an
observation (`mock_source.py`, `serpapi_source.py`, `yatra_source.py`)
sets both fields when constructing `RawFareObservation`;
`indigo_source.py` never returns real data at all (always
`SOURCE_UNAVAILABLE` — no live call is implemented), so it cannot violate
this. A real sample of scraper output (`data/raw/fares/*.jsonl`) had zero
missing values for either field. `advance_purchase_days` is therefore
cleanly derivable as `(flight_date − booking_date).days` on the
forecasting side, with no scraper-side change needed and nothing
invented — this stage would have stopped short of implementation if that
weren't true.

**Why this operates on raw observations, not `ForecastingDataset`.** By
the time raw observations are aggregated into a `ForecastingDataset` —
one row per period (or per route/period) — the per-observation
`booking_date` is gone, collapsed into the period/route index the same
way `fare_class`, `stops`, etc. already are. Booking-horizon partitioning
therefore has to happen on raw observations *before* aggregation:
`booking_horizon.py` partitions records by advance-purchase window, then
calls `build_forecasting_dataset()` once per window — reusing the exact
same aggregation path §18/§19 use, never reimplementing index math per
window. `data_access.py` and `series.py` are unmodified by this stage.

**Binning.** T+1 through T+45 is split into five 7-to-15-day buckets
(`T1_7`, `T8_14`, `T15_21`, `T22_30`, `T31_45`), inclusive on both ends,
covering every day in range exactly once (`tests/test_booking_horizon.py`
asserts this explicitly). Single-day granularity was considered and
rejected: at this project's current real-data volume (a handful of
scrape runs), single-day bins would mostly be empty or hold one
observation — not a meaningful window average. Five buckets keep each one
wide enough to hold multiple observations per scrape run while still
separating last-minute, one-to-two-weeks-out, three-weeks-out,
about-a-month-out, and five-to-six-weeks-out fare behavior — the coarse
shape the project's booking-horizon framing cares about. Boundaries are
plain 7-day steps (the last bucket widened to reach 45), not derived from
any statistical binning procedure — consistent with this codebase's
preference for explicit logic over cleverness.

**What is NOT a valid T+1..T+45 horizon, and how each case is counted —
never silently dropped or merged.** `BookingHorizonPartition` accounts
for every input record exactly once:
`missing_date_count` (no `flight_date`/`booking_date` — in practice
unreachable via the end-to-end `build_booking_horizon_datasets()` path,
since both are already required for a record to survive `ingest.py`'s
own structural filter; reachable directly through
`partition_by_booking_window()` on hand-built input),
`invalid_date_count` (present but not a parseable `YYYY-MM-DD` string),
`negative_horizon_count` (`booking_date` after `flight_date` — a data
error, never treated as `T+0`), and `out_of_range_count` (a valid,
non-negative horizon outside T+1..T+45, e.g. same-day or beyond 45 days
out). Each is surfaced in `BookingHorizonAnalysis.warnings` when nonzero.

**Per-window results, independent of each other.** `BookingWindowDataset`
carries one of three statuses per window: `STATUS_OK` (a
`ForecastingDataset` was built — its own rows may still show `None`
index values / non-OK statuses for thin periods or routes, exactly as
§9/§19 already handle), `NO_DATA` (zero records landed in this window —
no `ForecastingDataset` is attempted, nothing invented), or
`STATUS_INSUFFICIENT_DATA` (records existed but
`build_forecasting_dataset()` itself could not build a dataset from them,
e.g. every `flight_date` in the window falls outside the date-sanity
bounds of §11 with no explicit `periods` given — the underlying error is
preserved in `.error`). One window's `STATUS_INSUFFICIENT_DATA` never
blocks another window's `STATUS_OK` (`tests/test_booking_horizon.py`'s
`test_one_window_insufficient_data_does_not_block_others`).

**Real vs. synthetic provenance.** `BookingHorizonAnalysis` reports
`real_record_count`, `synthetic_record_count`, `is_synthetic_data` (True
only if every structurally-usable record across all windows is
`is_mock=True`), and `is_mixed_data` — the same fields and the same
mixed-input-raises-unless-`allow_mock=True` behavior as `ingest.py`'s
`ScraperIngestResult` (§18), applied once across the whole booking-horizon
run rather than being computed separately per window (a window's
provenance is a subset of the whole run's — if the whole run is real,
every window's data is real, so tracking it once is not a loss of
information).

**Scope note.** No forecasting or backtesting is layered onto individual
booking windows yet — this stage produces one `ForecastingDataset` per
window, which `national.py`/`route.py`'s existing functions can already
be called on directly if a per-window forecast is wanted. Whether that's
useful before more real data accumulates (so a window's own history is
long enough to forecast, not just describe) is left for a later stage to
decide, consistent with §13/§15's stance on not building ahead of the
data.

## 21. CPI year-over-year (YoY) comparison

**What changed.** `cpi_benchmark._yoy_comparison_status()` was, through
§20, an honest but unconditional stub — it always returned
`INSUFFICIENT_DATA` regardless of whether real YoY-comparable data
existed. Stage 4 replaces it with real YoY comparison logic, additive to
the existing MoM/correlation pipeline (§16) — nothing about MoM behavior
changed.

**Methodology, mirroring the existing MoM discipline exactly.** For each
period `P` in the our/MoSPI overlap (§16's `overlap_periods` — periods
present, non-missing, and trustworthy on both sides), the period exactly
12 calendar months prior is computed as
`index_engine.utils.shift_period(P, -12)` (correct calendar-month
arithmetic via `pandas.DateOffset`, not string subtraction). A YoY value
for `P` is computed **only if**:
1. That prior period is *also* in the our/MoSPI overlap (present on both
   sides, not just one) — a period individually present on one side but
   not the other never gets a fabricated YoY value; and
2. Both `P` and its prior period are `included_in_metrics` (i.e. neither
   was excluded by the MoSPI-imputation filter, §16) — a period that
   technically exists but is flagged untrustworthy is treated as absent
   for comparison purposes, the same standard the MoM logic already
   applies.

When both conditions hold, `our_yoy_pct`/`mospi_yoy_pct` are computed
from the same **rebased** values MoM already uses (`100 × (curr/prior −
1)`), and `yoy_difference_pct_points = our_yoy_pct − mospi_yoy_pct` is
stored on that period's `CPIPeriodComparison`. A period failing either
condition simply has `our_yoy_pct = mospi_yoy_pct = None` — never
interpolated, never estimated from a nearby period.

**Three distinct result states**, mirrored in `yoy_comparison_status`:
- `STATUS_INSUFFICIENT_OVERLAP` — no period at all is trustworthy on
  both sides (the same top-level condition that already short-circuits
  the whole comparison in §16; YoY inherits it rather than duplicating
  the check).
- `STATUS_INSUFFICIENT_DATA` — overlap exists, but no period has a valid
  12-months-prior pair (either genuinely absent from history, i.e. a
  calendar gap, or present but excluded as untrustworthy — both produce
  this same status, since either way there is no usable YoY signal).
- `STATUS_OK` — at least one period has a valid YoY pair.

**Summary fields on `CPIBenchmarkResult`**: `yoy_period_count` (how many
periods got a real YoY pair) and `mean_absolute_yoy_difference_pct_points`
(mirrors the MoM mean-absolute-difference gate — `None` below **2**
valid pairs, matching `MIN_PAIRS_FOR_MEAN_ABS_DIFF`'s MoM threshold via
its own `MIN_PAIRS_FOR_MEAN_ABS_YOY_DIFF` constant). A result with
exactly 1 valid pair reports `STATUS_OK` (it *is* a real, computed value)
but adds an explicit note that a single aligned period is "a data point,
not a trend" — the same illustrative-sample honesty already applied to
low-pair MoM correlations.

**Two failure modes kept distinct, by design and by test** (see
`tests/test_cpi_benchmark.py`):
- A **missing calendar period** (e.g. no data at all 12 months before
  `P`) — `P`'s prior period isn't in the overlap because it doesn't
  exist anywhere in either series.
- A **mismatched/untrustworthy period** (e.g. the prior period exists on
  both sides but MoSPI flagged it as imputed, so `exclude_mospi_imputed`
  marks it `included_in_metrics=False`) — `P`'s prior period exists but
  is excluded from comparison. Conflating these two into one "no YoY"
  bucket would hide *why* — one is a data-availability gap, the other is
  a data-quality judgment call this project already makes for MoM.

**Real-data status, honestly stated.** Against the project's actual
current data (`sample_fares.csv`'s Jan–Aug 2026 synthetic sample vs. the
real `cpi_1337.xlsx` extract), `yoy_comparison_status` is
`INSUFFICIENT_DATA` — there is no 2025 airfare data at all, so no period
can have a real 12-months-prior counterpart. This is not a bug: the
mechanism itself is exercised and asserted against exact hand-computed
values using local multi-year **synthetic** fixtures
(`tests/test_cpi_benchmark.py`, e.g. a fixture spanning 2025-01 through
2026-01 producing a hand-verified `our_yoy_pct = 10.0`,
`mospi_yoy_pct = 5.0`). As with every other synthetic-data result in
this module (§17), a computed YoY difference on synthetic input
describes how a fabricated series happens to move relative to MoSPI's
real CPI — never real-world validation. Real YoY validation requires
real airfare data spanning 12+ real months, which does not exist yet.

**What did not change.** `cpi_loader.py` was not touched (the MoSPI
period/index representation already supported this — no new parsing
needed). `data_access.py`, `series.py`, `index_engine`, `data_quality`,
and `scraper` were not touched — this stage is entirely local to
`cpi_benchmark.py`/`cpi_results.py`, reusing `national_index_series()`
and the existing rebasing/overlap machinery exactly as MoM already did.

## 22. Forecasting API layer

`api/forecasting_routes.py` exposes every forecasting stage above over
HTTP, following the exact same philosophy as the pre-existing
`api/main.py`/`api/schemas.py` wrapper around `index_engine`: a thin
JSON <-> Python translation layer with zero forecasting, backtesting,
index-aggregation, or booking-horizon-partitioning logic of its own.
Every route handler calls straight into `forecasting.*` (`national.py`,
`route.py`, `cpi_benchmark.py`, `booking_horizon.py`,
`data_access.build_forecasting_dataset`) and returns
`result.to_dict()` — the same pattern `api/main.py`'s existing
`/index/*` routes already use for `index_engine`. `api/main.py` itself
gained exactly two additive lines (`from .forecasting_routes import
router as forecasting_router` and `app.include_router(forecasting_router)`)
— every existing `/health`/`/index/*` route is byte-for-byte unchanged
and still covered by `tests/test_api.py`.

**Endpoints** (`api/forecasting_routes.py`, all under `/forecast`):

| Method | Path | Wraps |
|---|---|---|
| POST | `/forecast/national` | `national.forecast_national_index` |
| POST | `/forecast/national/evaluate` | `national.evaluate_national_baselines` |
| POST | `/forecast/route` | `route.forecast_route_index` |
| POST | `/forecast/route/evaluate` | `route.evaluate_route_baselines` |
| POST | `/forecast/routes` | `route.forecast_all_routes` |
| POST | `/forecast/routes/evaluate` | `route.evaluate_all_routes` |
| POST | `/forecast/cpi-benchmark` | `cpi_benchmark.compare_to_mospi_cpi` |
| POST | `/forecast/booking-horizon` | `booking_horizon.build_booking_horizon_datasets` |

**Request shape.** `/forecast/national`, `/forecast/route(s)(/evaluate)`,
and `/forecast/cpi-benchmark` all share `ForecastDatasetRequest`: the
same `observations`/`weights`/`config` schema `/index/calculate` already
accepts (`FareObservationIn`/`RouteWeightIn`/`IndexConfigIn` from
`api/schemas.py`, reused unchanged — not redefined), plus
`is_synthetic_data: bool` with **no default**, mirroring every
forecasting-layer function's own required-argument convention (§14):
the API cannot silently assume a caller's data is real. Each handler
builds a `ForecastingDataset` via `build_forecasting_dataset()` (raising
422 for `InsufficientDataError`, 400 for `ValueError` — the exact status
codes `/index/calculate` already uses for the same exceptions), then
calls the relevant forecasting function.

**Status is passed through, never overwritten.** A route/model with
`STATUS_INSUFFICIENT_DATA`, `STATUS_MODEL_NOT_APPLICABLE`, or a CPI
comparison with `yoy_comparison_status == INSUFFICIENT_DATA` is still a
`200 OK` HTTP response carrying that real status field in the body — the
API never converts "the forecasting layer had nothing trustworthy to
report" into either a fabricated numeric forecast or a misleading HTTP
error. `HTTPException` (400/422) is reserved for genuine request
problems: an unknown route name (`route_index_series`'s own
`ValueError`), an unsupported `horizon != 1`, an unknown model name, or
observations `index_engine` itself cannot build a dataset from.
`is_synthetic_data` (`is_synthetic_airfare_data` for the CPI endpoint)
is present on every response — never omitted, never defaulted.

**CPI endpoint: no client-supplied file path.** `/forecast/cpi-benchmark`
always loads this project's own bundled `data/benchmarks/cpi_1337.xlsx`
extract from a fixed server-side path — accepting an arbitrary path from
the request body would be a path-traversal / arbitrary-file-read surface
with no real benefit at this prototype stage. The MoM vs. YoY distinction
and the three-way `yoy_comparison_status` (`INSUFFICIENT_OVERLAP` /
`INSUFFICIENT_DATA` / `OK`, §21) are passed through in full — the API
does not collapse or reinterpret them.

**Booking-horizon endpoint.** `build_booking_horizon_datasets()` (§20)
takes scraper-JSONL file path(s) as its entry point, not in-memory
records — so `/forecast/booking-horizon` writes the posted observations
to a short-lived temp file and hands that path to the unmodified
function, then deletes the temp file in a `finally` block. No
windowing/partitioning math is reimplemented in the route handler. The
response summarizes each window's `status`/`record_count`/`error` plus
its per-period `national_index` and `quality_flags` — not the full
route-level panel, to keep the payload a reasonable size for an HTTP
response; a caller needing route-level booking-window detail should call
`booking_horizon.py` directly.

**Tests** (`tests/test_forecasting_api.py`, local fixtures only, no
network calls): successful national/route/all-routes forecasts;
insufficient-data reported honestly rather than fabricated; 400s for an
unknown route, `horizon != 1`, an unknown model, and malformed
observations; `is_synthetic_data` surfaced both `True` and `False`;
CPI benchmark response shape and its distinct MoM/YoY status fields;
booking-horizon response including a genuine `NO_DATA` window; and two
tests that monkeypatch `forecast_national_index`/`forecast_route_index`
at their import site and assert the route's response is exactly the
mocked return value — proof the handlers have no parallel forecasting
implementation of their own.

**What did not change.** `src/scraper`, `src/data_quality`, and
`src/index_engine` were not touched. `api/main.py`'s existing
`/health`/`/index/calculate`/`/index/timeseries` routes are unmodified
(all four pre-existing `tests/test_api.py` tests still pass unchanged).
No caching or persistence was added — every request recomputes from the
observations it was given, the same stateless pattern `/index/calculate`
already uses; this is a real limitation once a dashboard needs to avoid
re-uploading large observation sets per request, not something this
stage addresses.
