# SIH Pitch Notes: Differentiation and Judge Q&A

## Differentiation

**Basic version of this project:**
```
Scrape ticket prices -> show average price
```

**What this module actually does:**
```
Scraped airfare
    -> validation (every reject has a recorded reason)
    -> fixed-base Airfare Price Index (median representative fares, robust to outliers)
    -> REAL DGCA passenger-traffic weighting (not synthetic, not guessed)
    -> traffic coverage measurement (what % of India's actual air travel our routes represent)
    -> MoM / YoY inflation
    -> route-level inflation geography (heatmap-ready, missing != zero)
    -> airfare volatility (how unstable, not just how much it moved)
    -> booking-horizon volatility (last-minute vs. advance-purchase instability)
    -> relative airfare affordability (vs. an income indicator)
```

**The one-sentence claim:** we transform continuously collected airfare
observations into a multidimensional economic monitoring framework, not a
ticket-price display.

## Route Coverage Strategy (presentation-ready)

```
ROUTE COVERAGE STRATEGY

Current:
10 routes
8.8% passenger coverage

Recommended (near-term, Tier 1+2):
50 routes
30.7% passenger coverage

Expanded (stretch goal, Tier 1+2+3):
100 routes
44.5% passenger coverage
```

**The strongest message:** routes are prioritized using real DGCA
passenger traffic, not arbitrary or "add everything" selection — letting
us maximize statistical coverage while keeping automated data collection
computationally practical. The full coverage-vs-route-count curve (real
data, `examples/route_coverage_curve.png`) shows the classic diminishing-
returns shape: steep gains in the first ~50–100 routes, then a very long,
flat tail (90% coverage would need 695 of India's 2,228 real domestic
routes — not realistic for a hackathon-built scraper).

Top additional routes by real traffic (beyond the current 10): Delhi–Kolkata,
Delhi–Pune, Delhi–Mumbai(alt.), Delhi–Ahmedabad, Bengaluru–Kolkata,
Delhi–Srinagar, Bengaluru–Pune, Delhi–Guwahati, Delhi–Patna.

## The 5 strongest things to tell judges

1. **The weights are real, not invented.** Route importance comes from
   actual DGCA domestic passenger-traffic data (2025-06–2026-05 rolling
   window, ODbL-licensed extraction of DGCA's published statistics) — not
   a plausible-looking synthetic number.
2. **We measure our own representativeness and report it honestly.** Our
   10 scraped routes represent 8.8% of India's domestic passenger
   traffic — we say this out loud rather than letting "we scraped 10
   routes" imply more coverage than it has. Honesty about a small number
   is more credible than an inflated one.
3. **Inflation and importance are kept separate, on purpose.** Every
   route in our output carries its inflation rate, its real traffic
   weight, and its exact contribution to the national number side by
   side — so "which route moved the most" is never confused with "which
   route mattered most," a distinction most naive projects miss entirely.
4. **Volatility is a second, genuinely different signal.** A route can
   have a flat index and still be wildly unpredictable booking to
   booking; our booking-horizon breakdown can show last-minute fares are
   both pricier and far more erratic — a distinctive, explainable finding.
5. **We show our own robustness, unprompted.** A sensitivity analysis
   across 9+ configurations (representative-fare method, outlier
   handling, aggregation method, synthetic vs. real weights) shows under
   3% spread — the headline number isn't an artifact of one arbitrary
   choice, and we can show the table if asked.

## 20 likely judge questions

**Statistical methodology**
1. *Why median instead of mean for the representative fare?* — Airfares
   are right-skewed; median resists extreme fares. Demonstrated in tests
   (one ₹500,000 outlier barely moves the median, drags the mean past ₹100,000).
2. *Why arithmetic aggregation instead of geometric?* — Matches how
   headline CPI aggregates with fixed base-period weights (Laspeyres-style)
   and decomposes exactly into route contributions; geometric implicitly
   assumes route substitution, weaker for point-to-point flights.
3. *How do you know the index isn't sensitive to one arbitrary setting?*
   — `examples/sensitivity_analysis.py`: 9 configurations, <3% spread.
4. *Why a fixed base period instead of a chained index?* — Simplicity and
   transparency for a prototype; chaining is a documented future step.

**DGCA weights**
5. *Where do the weights actually come from?* — DGCA's own published
   monthly domestic statistics, via an ODbL-licensed extraction pipeline
   (`data/traffic/README.md` has the exact chain, retrieval command, and date).
6. *Why not use AAI airport data?* — Airport totals can't isolate a
   specific city pair's traffic; only usable as a cross-check.
7. *Are these official CPI weights?* — No — route-importance weights
   derived from passenger traffic, explicitly not expenditure weights,
   which is what official CPI weighting requires.
8. *Why are BLR-DEL and DEL-BLR treated separately?* — Fares are
   directional and DGCA's data is directional; merging would hide real
   asymmetries.
9. *Why a 12-month window and not the latest single month?* — A single
   month can be distorted by holidays/weather/disruptions; 12 months is
   more stable, and the window is computed from the latest data available,
   never hard-coded.
10. *What does "8.8% traffic coverage" actually mean, and why so low?* —
    India has 2,228 distinct real-world directional domestic routes; our
    10 scraped routes, while major trunk routes, are a small fraction of
    that universe by count (though a larger fraction by passenger volume
    than 10/2228 would suggest, since trunk routes carry disproportionate traffic).

**Volatility**
11. *What's the difference between the price index and volatility?* — The
    index tracks whether the typical price moved; volatility tracks how
    dispersed prices are around that typical price, independent of trend.
12. *Why coefficient of variation over log-return volatility?* — CV needs
    only one period's observations, appropriate with limited scraping
    history; log-return volatility (also implemented) needs multiple
    months and is offered as the data matures.
13. *Are your HIGH/LOW volatility thresholds official?* — No — explicitly
    documented prototype cutoffs (CV 0.10 / 0.25), not derived from a
    large historical calibration.

**Route inflation / heatmap**
14. *Why show a heatmap at all — isn't the national number enough?* — The
    national number hides geography; the heatmap answers "where," and
    combined with traffic weight, "does it matter."
15. *Why are some cells in the heatmap blank instead of zero?* — A route
    with no data has an unknown inflation rate, not a zero one; treating
    it as zero would fabricate a value.

**Affordability**
16. *Is this a real affordability measure?* — No — "Relative Airfare
    Affordability Index," explicitly not household affordability, and
    the demo income series is synthetic and labelled as such.
17. *What would it take to make this real?* — A validated Indian
    wage/income index as input; the formula and pipeline are already
    real, only the input data is a placeholder.

**Data quality / scraping / missing data**
18. *What happens when a route has too few observations?* — Flagged
    `INSUFFICIENT_DATA`, excluded from the index, never faked, and
    counted in the reported quality metrics.
19. *How do you handle a route that appears or disappears?* — `NEW_ROUTE`
    / `DISCONTINUED` statuses, both excluded from the index calculation
    but visible in the output and quality flags.
20a. *Why only 10 routes / why not scrape all 2,228?* — Diminishing
    returns: the top 50 routes already capture 30.7% of national traffic;
    reaching 90% would need 695 routes. We prioritize by real passenger
    traffic and recommend expanding to Tier 1+2 (50 routes) as a realistic
    next step, not "as many routes as possible."
20b. *Does 80% traffic coverage mean 80% CPI representativeness?* — No,
    explicitly not — passenger traffic is a route-importance measure for
    this experimental index; CPI representativeness requires
    expenditure/consumption weighting, a different and stricter standard.
20. *Could this genuinely augment official CPI one day?* — Only after:
    real expenditure-based (not traffic-based) weights, a larger
    continuously-running scraper giving stable monthly samples, and
    methodological sign-off from a statistician on seasonal adjustment
    and elementary aggregation conventions — all stated explicitly in
    `docs/methodology.md` §19, not glossed over.
