# Airfare Price Index — Methodology

**Status: SIH prototype.** This document describes the statistical
methodology implemented in `index_engine`. It is a defensible, transparent
prototype methodology — it is **not** an official statistic, has not been
validated against real passenger-volume data, and must never be presented
to anyone as an official CPI sub-index.

> This is a prototype Airfare Price Index designed with CPI-compatible
> principles, intended to augment existing CPI analysis — not to replace
> or claim to be part of the official CPI itself.

---

## 1. What this index measures

The engine turns many individual fare observations (one row per
scraped/quoted fare) into a single number per month that tracks how
expensive it is, on average and across a weighted basket of routes, to fly
domestically in India relative to a fixed base month (index = 100).

## 2. Why a raw average of all ticket prices is insufficient

A simple average of every scraped fare mixes together things that are not
the same product: a 45-minute Delhi–Jaipur hop and a 3-hour Bangalore–Delhi
flight, a last-minute walk-up fare and a fare booked two months out, a
business-class ticket and a basic economy fare. If the mix of *what got
scraped* changes month to month — more long-haul routes scraped this
month, say — the raw average moves for reasons that have nothing to do
with airfares actually getting more expensive. A price index has to hold
the *basket* fixed and only let *prices* move.

## 3. Fare standardization

**Prototype definition:** total mandatory payable one-way fare for one
adult passenger, including mandatory taxes and fees, excluding optional
add-ons (baggage, seat selection, insurance). This is `total_fare` in the
input schema, controlled by `IndexConfig.fare_field` so a different
definition (e.g. base fare only) can be swapped in without touching any
other module.

## 4. Representative fare per route/period

Many observations exist for the same route in the same month (different
airlines, times of day, booking dates). These are collapsed into one
**representative fare** before anything else happens.

Default: **median**. Airfares are strongly right-skewed — a handful of
last-minute or premium fares can be many multiples of the typical fare —
so the median resists being pulled by those extremes. `mean` and
`trimmed_mean` are also implemented and selectable via
`IndexConfig.representative_method` for sensitivity comparison.

## 5. Route-level price relative and index

For a route, given a base-period representative fare `P₀` and a
current-period representative fare `Pₜ`:

```
Price Relative = Pₜ / P₀
Route Index    = 100 × (Pₜ / P₀)
```

Example: `P₀ = ₹5,000`, `Pₜ = ₹5,500` → Route Index = 110.

## 6. Route weights

Weights determine how much each route's movement counts toward the
national number. They come from an external, swappable table
(`origin, destination, weight, effective_from, effective_to, source`) —
**never hard-coded inside the calculation logic.**

For this prototype, `generate_synthetic_weights()` produces illustrative
weights (metro-to-metro trunk routes weighted 3× regional routes) and
tags every row `source = "SYNTHETIC_DEMO_ONLY"`. Before any real use, this
must be replaced with actual passenger-volume or expenditure-share data —
the engine does not care where the weights table came from, only that it
has the right columns.

## 7. National aggregation

Route indices are combined into one national index using weights
normalized to sum to 1.

**Default — arithmetic (Laspeyres-style):**

```
National Index = Σ (weight_i × RouteIndex_i)
```

This mirrors how headline CPI aggregates elementary indices using
fixed base-period expenditure weights, and is straightforward to explain
and to decompose into contributions (§10). "Laspeyres-style" here
describes the general index-theory pattern (a weighted arithmetic mean of
price relatives with fixed base-period weights) — it is **not** a claim
that this engine replicates India's actual official CPI computation
step-for-step, nor that our DGCA-derived traffic weights (§15) are the
same kind of weight CPI uses (they are traffic-based, CPI's are
expenditure-based; see §15 and §19 for the explicit distinction).

**Alternative — geometric:**

```
National Index = 100 × exp( Σ weight_i × ln(RouteIndex_i / 100) )
```

The geometric mean is pulled less by any single route spiking, but it
implicitly assumes travellers substitute between routes (fly BOM–DEL
instead of BLR–DEL because it got relatively cheaper) — a weaker
assumption for point-to-point air travel than it is for, say,
substitutable grocery items — and it is harder to decompose into
"route X caused Y% of the change." We default to arithmetic for that
reason and expose `IndexConfig.aggregation_method` to switch.

## 8. Base period

Configurable via `AirfarePriceIndex(base_period=...)`. Never hard-coded
into the algorithm — every route's index and the national index are always
computed relative to whatever base period is configured.

## 9. Month-over-month and year-over-year change

Because the index is a simple ratio to a fixed base, month-to-month or
year-to-year comparisons are just ratios of two index values (the base
period cancels out):

```
MoM % = (NationalIndex[t] / NationalIndex[t-1 month] − 1) × 100
YoY % = (NationalIndex[t] / NationalIndex[t-12 months] − 1) × 100
```

If a comparison period's index cannot be computed (e.g. fewer than 12
months of history exist yet), the corresponding change is returned as
`None` rather than a fabricated number.

## 10. Contribution analysis

For the (default) arithmetic aggregation, each route's contribution to the
national index's month-over-month point change is:

```
Contribution_i = weight_i × (RouteIndex_i[t] − RouteIndex_i[t-1 month])
```

`weight_i` here is **not** the raw table-wide `weight_normalized` (which
sums to 1.0 across every route in the weights table, whether or not it has
data this period). §9's national index itself renormalizes over only the
routes that are `OK` *in that period* — dividing by the sum of
`weight_normalized` over that usable subset, not by 1.0, since coverage
below 100% is the normal case, not an edge case (see the 8.8%
traffic-coverage example in §13). `contribution.py` renormalizes by that
same usable-subset total before multiplying, so `weight_i` above always
means "this route's share of the routes actually usable this period," not
its share of the full weights table.

With that renormalization, these contributions sum exactly to the
national index's point change **provided the same set of routes is `OK`
in both periods being compared** — which is what makes "route X drove Y
points of this month's move" a provable statement rather than a hand-wavy
one, for the routes that condition holds for. If route composition
*changed* between the two periods (a route went from `OK` to not, or vice
versa), the engine raises a quality flag on `IndexResult.quality_flags`
saying exactly that, and the contribution decomposition is only partial
for the affected routes — part of that period's MoM/YoY move reflects the
compositional shift itself, not pure price movement. (For the geometric
aggregation this decomposition is only approximate regardless, since a
weighted geometric mean's change does not split linearly across
components — this is stated explicitly in the code and output.)

## 11. Outlier handling

Outliers are detected *within each route/period group* (a fare that's
normal on a trunk route may be extreme on a thin regional one), using one
of:

- **IQR** (default): flag fares outside `[Q1 − k·IQR, Q3 + k·IQR]`
- **MAD**: flag fares whose modified z-score (based on median absolute
  deviation) exceeds a threshold
- **Percentile trimming**: flag fares outside configured percentile bounds

No observation is ever silently deleted — every removal is tagged with a
reason (`OUTLIER_IQR`, `OUTLIER_MAD`, `OUTLIER_PERCENTILE`,
`INVALID_FARE`, `DUPLICATE`, `MISSING_REQUIRED_FIELD`, `INVALID_DATE`,
`SAME_ORIGIN_DESTINATION`, `IMPOSSIBLE_BOOKING_HORIZON`) and counted in the
returned cleaning report.

## 12. Missing and incomplete data

A route is classified into exactly one status per calculation, and only
`OK` routes contribute a number to the national index:

| Status | Meaning |
|---|---|
| `OK` | Sufficient data in both base and current period; index computed |
| `NEW_ROUTE` | No base-period data at all (route didn't exist / wasn't observed then) |
| `DISCONTINUED` | Had base-period data, but none in the requested period |
| `NO_BASE_DATA` | No data in either period (route unknown to the dataset) |
| `INSUFFICIENT_DATA` | Data exists but below `min_observations_per_route_period` |

No missing price is ever invented or interpolated. `coverage_rate` in the
result reports what *fraction of total route weight* had a usable index —
a weighted figure, since a major trunk route missing data matters far more
than a minor one.

## 13. Booking horizon

A fare booked 1 day before departure and a fare booked 45 days before
departure for the same flight are not the same product — airline
yield-management pricing makes booking horizon a first-order driver of
price, arguably as large as the route itself.

Observations are bucketed into `0-3, 4-7, 8-14, 15-30, 31-60, 61+` days
(the boundary is deliberately mutually exclusive — day 60 falls in
`31-60`, so the open-ended tail bucket is labelled `61+`, not `60+`, to
match what it actually contains).
The engine can either:

1. **Pool all horizons together** (default) — larger sample sizes, more
   stable representative fares, but the index partly reflects shifts in
   *when* people are booking rather than pure price movement.
2. **Restrict to one horizon bucket** via
   `IndexConfig(booking_horizon_filter="15-30")` — a cleaner
   like-for-like comparison, at the cost of a smaller sample per
   route/period (more routes may fall into `INSUFFICIENT_DATA`).

## 14. Limitations (prototype, stated explicitly)

- Route weights are synthetic placeholders, not real passenger volumes.
- No seasonal adjustment.
- No adjustment for cabin class mix, ancillary revenue, or dynamic
  currency effects (assumes INR throughout).
- Outlier thresholds and the minimum-observation cutoff are configured
  defaults, not empirically tuned against a large historical dataset.
- Coverage depends entirely on what the scraper actually collects; a gap
  in scraping shows up as `INSUFFICIENT_DATA` / `NO_BASE_DATA`, not as a
  corrected number.

## 15. DGCA Passenger-Traffic Weighting

**These are DGCA-derived passenger-traffic route-importance weights, not
official CPI expenditure weights.** Full provenance and known data
characteristics are documented in `data/traffic/README.md`; the summary:

1. **Why passenger traffic, not synthetic weights.** A route's importance
   to a *national* airfare index should reflect how many people actually
   fly it. DGCA's monthly domestic city-pair statistics (accessed via the
   ODbL-licensed `Vonter/india-aviation-traffic` extraction of DGCA's
   published reports — see `data/traffic/README.md`) give exactly that:
   real passenger counts per city pair per month, 2015 onward.
2. **Why not AAI airport totals.** An airport's total passenger count
   mixes every route through that airport together; it cannot tell you
   how many of those passengers flew any *specific* city pair. Route
   weights need route-level data, so AAI airport totals are unsuitable
   here (useful only as an independent cross-check, not as the weight
   source itself).
3. **Why directional city pairs are preserved.** DGCA's data already
   reports `PaxToCity2` and `PaxFromCity2` separately, and airfares
   themselves are directional (a BLR→DEL fare and a DEL→BLR fare can
   differ), so `index_engine.traffic` never merges the two directions.
4. **Why a rolling 12-month window.** A single month can be distorted by
   holidays, weather, or a temporary route suspension. The default window
   is the most recent 12 months *available in the data* (never a
   hard-coded date range — see `traffic.latest_available_period` and
   `traffic.rolling_window`), which as of this writing lags about 2–3
   months behind the calendar month because that's how far behind DGCA's
   own published statistics run.
5. **National weight vs. covered-route weight — mandatory distinction.**
   `national_weight` = a route's passengers ÷ **all** eligible domestic
   passengers nationwide in the window (2,228 distinct directional routes
   as of the 2025-06–2026-05 window used in this repo's examples). This
   is the route's true share of India's domestic air travel. The
   `weight` actually fed into `AirfarePriceIndex` is the
   **covered-route renormalized weight** — `national_weight` rescaled so
   the routes we actually have airfare observations for sum to 1. These
   answer different questions and must never be conflated: national
   weight says "how big is this route nationally"; covered weight says
   "how much should this route count *among the routes we can measure*."
6. **Traffic coverage metric.** `traffic_weight_coverage` = the sum of
   `national_weight` across only the routes we have usable airfare data
   for. In this repo's 10-route example universe (real data,
   2025-06–2026-05 window): **8.8%** of India's domestic passenger
   traffic — a small, honest number precisely because there are 2,228
   distinct real-world directional city pairs and this prototype only
   scrapes 10 of them. This is a materially stronger representativeness
   argument than "we have 10 routes" on its own, and it is honest in
   both directions — it doesn't inflate a small sample into a misleading
   percentage.
7. **City name ↔ IATA code mapping.** DGCA publishes city names
   ("DELHI"), airfare data uses IATA codes ("DEL"). `index_engine.city_mapping`
   is a small, hand-verified, hand-documented dictionary — no fuzzy
   matching. Two Mumbai-related entries (`MUMBAI (MUMBAI)`,
   `MUMBAI (NAVI MUMBAI)`) are deliberately left unmapped rather than
   guessed into `BOM`; see the module docstring for why.
8. **Limitations.** Real DGCA statistics lag the current month by
   several months, so weights are always slightly stale relative to
   "right now" — a real limitation for a *real-time* index, mitigated but
   not eliminated by the rolling-window approach. The mapping only covers
   the handful of cities this prototype's route universe uses; extending
   route coverage requires verifying and adding more mapping entries by
   hand, deliberately, one at a time.

## 16. Airfare Volatility

Implemented in `index_engine.volatility`, independent of the price index
formula. Volatility answers "how unstable is the price," which is a
different question from "did the price go up" — a route can have a stable
index (no clear trend) while still being highly volatile (fares swinging
wildly month to month or booking to booking).

- **Default methodology: coefficient of variation** (std-dev ÷ mean of a
  route's fares within one period), chosen because it only needs a single
  period's cross-sectional observations — appropriate for a project that
  may have only a few months of live data — and it matches the intuitive
  definition directly.
- **Alternative: log-return standard deviation** across a route's
  representative-fare time series, the standard financial-volatility
  definition, available once enough monthly history accumulates
  (`VolatilityConfig(method="log_return_stddev")`).
- Thresholds (`low_threshold=0.10`, `high_threshold=0.25`) are stated
  **prototype** cutoffs, not derived from a large historical calibration
  — documented as such in the code, not presented as an official
  statistical standard.
- Booking-horizon volatility (breaking the same calculation down by the
  `0-3 ... 61+` day buckets) is one of this project's more distinctive
  analytical outputs — it can show, for example, that last-minute fares
  are both higher on average *and* far more erratic than advance-purchase
  fares, which a single volatility number would hide.

## 17. Route-Level Inflation and the Inflation/Importance Distinction

Implemented in `index_engine.route_analysis`, built entirely on top of
values the engine already computes (`route_indices`, `route_contributions`)
— no duplicate formulas.

**The central point, and a genuine SIH talking point:** high inflation on
a route and high importance to the national number are not the same
thing. `RouteInflationRow` always carries `mom_inflation_pct`,
`yoy_inflation_pct`, `traffic_weight` (real DGCA share), and
`contribution` (exact point contribution to the national MoM move)
together, specifically so a dashboard — or a judge's question — can't
conflate "this route moved the most" with "this route mattered the most."

- `route_analysis.inflation_matrix()` produces an origin×destination
  matrix for MoM or YoY. Missing routes are `NaN`, never `0` — a route
  with no data is not a route with zero inflation, and treating it as
  zero would be a fabrication.
- `route_analysis.route_map_objects()` attaches lat/lon (from
  `index_engine.geo_metadata`, kept entirely separate from any
  statistical calculation) for a frontend map; routes with an unmapped
  city are skipped rather than guessed.
- `route_analysis.top_rankings()` reuses the *same* contribution numbers
  `index_engine.contribution` already computed — there is only one
  contribution formula in this codebase.

## 18. Relative Airfare Affordability Index

Implemented in `index_engine.affordability`. Answers a narrower, more
defensible question than "can households afford to fly": did airfare rise
faster or slower than a chosen income/wage indicator?

```
Relative Affordability Index = (Airfare Index / Income Index) x 100
```

Example: Airfare Index 110, Income Index 105 → 104.76, read as "airfare
rose about 4.76 percentage points faster than this income indicator" —
**not** as "households can afford 4.76% less air travel."

- This is called the **Relative Airfare Affordability Index**, never an
  "official affordability index," because no validated Indian
  household-income or wage series backs it in this prototype.
- If no income data is supplied for the requested period, the result
  status is `DATA_UNAVAILABLE` — nothing is invented, and the core price
  index works completely independently of this module (affordability is
  always optional).
- The example demo (`examples/analytics_demo.py`) uses an income series
  explicitly labelled `SYNTHETIC_DEMONSTRATION_DATA`. Replacing it with a
  real, validated Indian wage/income series is required before any real
  affordability conclusion should be drawn from this module's output.

## 19. Route Coverage Expansion

`index_engine.route_selection` ranks the full real DGCA route universe
(2,228 distinct directional routes, 2025-06–2026-05 window) by traffic to
answer: what should the scraper cover next, and where are the diminishing
returns?

**Two different "10 routes" numbers appear in this project's reports, and
they are not the same thing — this distinction matters and is stated
explicitly to avoid an apparent contradiction:**

- **8.8%** = the traffic coverage of our *actual* current 10-route demo
  universe (BLR-DEL, DEL-BOM, BOM-BLR, DEL-HYD, BLR-HYD, MAA-DEL, DEL-MAA,
  BOM-DEL, CCU-DEL, BLR-BOM) — chosen for illustrative metro-pair variety,
  not because they are literally the 10 highest-traffic routes nationwide.
  This is the number quoted everywhere else in this repo as "current
  coverage" (`traffic.build_dgca_weights`'s `traffic_weight_coverage`
  for those specific 10 routes).
- **10.4%** (first row of the table below) = the coverage achieved by the
  hypothetical *best possible* 10 routes ranked purely by real traffic —
  i.e. what `route_selection.coverage_at_n(ranked, 10)` returns. It is a
  planning ceiling for "if we could only pick 10 routes, what's the most
  we could cover," not a description of what the demo currently covers.

The table below (`coverage_scenarios`) is entirely about that second,
best-possible-selection question — it ranks ALL 2,228 routes by traffic
and reports cumulative coverage of the top N, regardless of which routes
this repo's demo actually uses:

| Top N routes by traffic | Traffic coverage | Incremental gain |
|---:|---:|---:|
| 10 | 10.4% | — |
| 20 | 17.4% | +7.1pp |
| 30 | 22.7% | +5.3pp |
| 50 | 30.7% | +8.0pp |
| 75 | 38.3% | +7.6pp |
| 100 | 44.5% | +6.2pp |
| 150 | 54.1% | +9.6pp |
| 200 | 61.5% | +7.4pp |
| 300 | 71.8% | +10.3pp |
| 500 | 83.3% | +11.5pp |

Minimum routes for a target coverage: 25% needs 36 routes, 50% needs 127,
60% needs 189, 70% needs 279, 80% needs 428, 90% needs 695 — the long tail
of India's ~2,200 real domestic city pairs is genuinely long, so chasing
80–90% coverage is not a realistic scraper target for a prototype.

**Why we don't just scrape every route.** The marginal traffic gained per
additional route drops steadily (roughly 0.87%/route in the top 20, down
to ~0.06%/route beyond 300) while scraper engineering and data-quality
complexity per route stays roughly constant. Past a few hundred routes the
long tail buys very little additional statistical representativeness for
a lot of additional scraping surface area.

**Priority tiers** (`route_selection.assign_tiers`, cutoffs at rank 20/50/100
— chosen at the visible marginal-return breakpoints above, not round numbers):

- **Tier 1 — Essential** (routes 1–20, 17.4% coverage): major metro trunk routes.
- **Tier 2 — High value** (21–50, 30.7% coverage): remaining big-city and rising secondary-city routes.
- **Tier 3 — Expansion** (51–100, 44.5% coverage): broader secondary-city coverage, most of the geographic diversity gain happens here.
- **Tier 4 — Long tail** (101+): individually low-value; not worth scraper complexity for this prototype.

**Bidirectional summary for prioritization only.** `bidirectional_summary()`
combines both directions of a city pair (e.g. `BENGALURU <-> DELHI`) purely
to help the scraper team prioritize *which city pairs* to build coverage
for — the actual price-index weights stay directional (`BLR->DEL` and
`DEL->BLR` remain separate rows all the way through).

**Geographic gaps found in the real data.** Ranking by route alone hides
cities whose traffic is spread across many individually-smaller routes.
Computed from the real network: **Jaipur, Nagpur, and Goa** have
substantial total passenger traffic but no single route cracking the top
100 by route-level traffic. Goa is additionally split across at least four
separate DGCA naming variants (`GOA`, `GOA (DABOLIM, SOUTH GOA)`,
`GOA (MOPA, NORTH GOA)`, and the older `DABOLIM` used in earlier route-level
rows) — mirroring the Mumbai-naming issue in §15, and left unmerged for
the same reason: merging distinct published entries would be a guess, not
a verified mapping.

**Recommended target.** Tier 1+2 (50 routes, 30.7% coverage) is a
realistic near-term production target for a scraper built during a
hackathon timeline. Tier 1+2+3 (100 routes, 44.5%) is a reasonable stretch
goal if scraper infrastructure scales well. Beyond 100 routes, coverage
gains flatten relative to the added engineering surface.

**Outputs:** `data/routes/scraper_route_priority.csv` (top 150, ranked and
tiered, tagged `DGCA_DERIVED_ROUTE_PRIORITY` — never described as an
official DGCA recommendation) and `data/routes/recommended_routes.json`
(top 100, machine-readable, IATA-mapped where a verified mapping exists;
`null` IATA fields mark cities needing a mapping decision, e.g. the
`MUMBAI (MUMBAI)` variant — 12 of the top 100 routes fall in this category
and are deliberately left unmapped rather than guessed).

**Distinguishing coverage metrics — do not conflate:** `10 routes` (a
route *count*) and `8.8% traffic coverage` (a *passenger-weighted* share)
answer different questions; a route count alone says nothing about how
much of India's actual air travel it represents. And **critically: traffic
coverage is not CPI representativeness.** Passenger traffic is a
route-importance measure for this experimental airfare index; official
CPI representativeness would require expenditure/consumption-based
weighting and methodological validation this prototype does not have.

## 20. Path to alignment with official CPI methodology

To move from prototype to something that could genuinely augment the
official CPI, the team would need: (a) genuine expenditure-based weights —
even the real DGCA passenger-traffic weights in §15 are route-*importance*
weights, not expenditure weights, and CPI weighting is expenditure-based
by definition, (b) a validated, larger and continuously-running scraping
pipeline giving stable monthly sample sizes per route, (c) a decision —
made with a statistician, not inferred from code — on seasonal adjustment
and on whether the elementary aggregation should follow CPI's own
elementary index conventions (e.g. Jevons/geometric at the lowest level),
(d) a review of the outlier and minimum-sample thresholds against several
years of real data rather than the defaults chosen here, and (e) for the
volatility and affordability extensions specifically: volatility
thresholds calibrated against real historical distributions rather than
the round-number prototype cutoffs in §16, and a validated Indian
income/wage series before §18's affordability number means anything
beyond a worked example.
