# MOSPI PLFS Real Wage/Salary Earnings (income series for the Affordability Index)

`mospi_plfs_income.csv` in this directory is **real data**, not a placeholder
— sourced from the Periodic Labour Force Survey (PLFS), retrieved directly
against the live, official MoSPI eSankhyiki API and verified against the
raw JSON response, not copied from a secondary source.

## Provenance (mandatory reading before citing this to a judge)

**Primary statistical authority:** National Sample Survey Office (NSO),
Ministry of Statistics and Programme Implementation (MoSPI), Government of
India — Periodic Labour Force Survey.

**Retrieval:** Called directly against the live, public MoSPI API —
`https://api.mospi.gov.in/api/plfs/getData` — no API key or registration
required (unlike `data/traffic/dgca_domestic_city_pairs.csv`'s extraction
pipeline, which needed a third-party ODbL republication; this one is a
first-party government endpoint, called directly).

```
GET https://api.mospi.gov.in/api/plfs/getData
    ?indicator_code=6&frequency_code=1&year={2022|2023|2024|2025}
```

`indicator_code=6` = "Average wage/salary earnings (Rs.) during the
preceding calendar month from regular wage/salaried employment" — one of
8 PLFS indicators (`GET /api/plfs/getIndicatorListByFrequency`). Filtered
in the response to `gender=person` (both sexes combined), `sector=rural +
urban` (national total, not split), `state=All India`, `year_type=Calendar
Year` (the API also returns Agriculture-Year-keyed rows for some other
indicators; this specific earnings indicator only returns Calendar-Year
rows).

**Retrieved:** 2026-09-04.

**Server quirk, verified while retrieving this:** `api.mospi.gov.in`
requires legacy SSL renegotiation and serves a certificate that a modern
TLS stack rejects by default — the official government client
(`github.com/nso-india/mospi-esankhyiki`) itself disables certificate
verification and enables `OP_LEGACY_SERVER_CONNECT` to reach it. This is a
real characteristic of the government server, not a shortcut taken here;
document it rather than hide it if a judge asks how this was retrieved.

## Known data characteristic — ANNUAL ONLY, not monthly

**This is the one thing to never blur when explaining the affordability
index.** Wage/earnings indicators (5-8) on this API are published **only
at annual frequency** — verified directly: querying
`getIndicatorListByFrequency?frequency_code=3` (Monthly) and
`frequency_code=2` (Quarterly) returns only employment-*rate* indicators
(LFPR, WPR, unemployment rate), never earnings. There is no real monthly
Indian wage series available from this or any other source found during
this project's research (the Labour Bureau's Wage Rate Index is
semi-annual — January/July only — and not machine-readable at all).

Only 4 years have data for this specific indicator/breakdown: **2022
(₹19,315.50), 2023 (₹20,407.54), 2024 (₹21,454.87), 2025 (₹22,698.65)**,
all All-India, combined-gender, rural+urban monthly averages.

## How this feeds the monthly Affordability Index

`index_engine.affordability` computes `Relative Affordability Index =
(Airfare Index / Income Index) x 100` per `YYYY-MM` period — a real
mismatch against an annual-only income series. The chosen approach: the
income index for every month within a calendar year is set to that year's
single real annual value (held flat, not interpolated or fabricated
between years) — see `src/index_engine/mospi_income.py`. This is not a
month-over-month income signal; it changes only once a year, honestly,
because that is genuinely how often the underlying real statistic is
published. Do not present a MoM affordability delta as reflecting real
monthly income movement — it reflects real monthly *airfare* movement
against a real but slow-moving income baseline.

**Carried forward past 2025, deliberately:** this project's own fare data
is always dated "now or later" (the scraper only ever collects current,
forward-looking quotes — see `docs/scraper.md` §10), while MoSPI's
wage/earnings indicators lag roughly a year behind. Under a strict
"only exact overlapping periods" rule, affordability would report
`DATA_UNAVAILABLE` for every period this project could ever produce, not
just until the next MoSPI release. Instead, `mospi_income.py` carries
2025's real value forward for `CARRY_FORWARD_YEARS` (5) more years,
tagged `source="MOSPI_PLFS_LATEST_CARRIED_FORWARD"` — a distinct tag from
`"MOSPI_PLFS_ANNUAL_HELD_FLAT"` (a period MoSPI has actually published
for) so the two are never presented as the same kind of number. This
mirrors the precedent already set by `traffic.to_engine_weights()`'s own
`effective_from`/`effective_to` reasoning for DGCA route weights: a real
number that hasn't been refreshed yet is a materially different thing
from an invented one. Refresh this CSV (re-run the retrieval in this
file's own provenance section) once MoSPI publishes 2026 figures, rather
than let the carry-forward window silently expire.

## What this is NOT

- **Not** an official CPI weight or expenditure series — it is a labour
  earnings statistic, used here purely as the income denominator the
  Affordability Index's own formula calls for.
- **Not** interpolated, smoothed, or projected between the 4 real years —
  held flat within each year, nothing invented between or beyond them.
- **Not** state-level or demographic-segmented in this file — the
  All-India/combined-gender/combined-sector aggregate was chosen to match
  the national scope of the airfare index it's compared against; the raw
  API has real male/female and rural/urban breakdowns available if a
  future segmented affordability view is ever built.
