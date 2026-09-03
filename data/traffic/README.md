# DGCA Domestic City-Pair Passenger Traffic

`dgca_domestic_city_pairs.csv` in this directory is **real data**, not a
placeholder — it is used as-is by `index_engine.traffic` to compute route
importance weights.

## Provenance (mandatory reading before citing this to a judge)

**Primary statistical authority:** Directorate General of Civil Aviation
(DGCA), Government of India — publishes Monthly Statistics (Domestic Air
Transport) on https://www.dgca.gov.in/.

**Extraction pipeline (not the authority itself):** DGCA publishes these
statistics as monthly XLSX reports, not a queryable API or a single
machine-readable file. This repo does not scrape DGCA directly; instead it
uses the already-extracted, aggregated CSV maintained at
[`Vonter/india-aviation-traffic`](https://github.com/Vonter/india-aviation-traffic)
(`aggregated/domestic/city.csv`, commit as of 2026-08-31), which
transparently fetches and parses DGCA's own monthly XLSX releases via
scripts in that repository (`dgca/fetch.sh`, `dgca/parse.sh`,
`dgca/aggregate.py`).

**License:** ODbL-1.0 (Open Database License). Required attribution per
that repository: *"Users of this data should attribute DGCA
(https://www.dgca.gov.in/digigov-portal/) and Ministry of Civil Aviation."*
Any adapted/derivative database must also be offered under ODbL.

**Retrieved:** 2026-08-31, via:
```bash
curl -L -o data/traffic/dgca_domestic_city_pairs.csv \
  https://raw.githubusercontent.com/Vonter/india-aviation-traffic/main/aggregated/domestic/city.csv
```

**Do not describe this file as "official DGCA data downloaded directly
from DGCA."** The correct, precise description is:

> DGCA-sourced domestic city-pair passenger traffic, via the
> Vonter/india-aviation-traffic ODbL-licensed extraction of DGCA's
> published monthly statistics.

## Schema (as delivered, unmodified)

| Column | Meaning |
|---|---|
| `Year` | Calendar year |
| `Month` | 1–12 |
| `City1`, `City2` | City names as published by DGCA (not IATA codes — see `index_engine.city_mapping`) |
| `PaxToCity2` | Passengers who flew City1 → City2 that month |
| `PaxFromCity2` | Passengers who flew City2 → City1 that month |
| `FreightToCity2`, `FreightFromCity2`, `MailToCity2`, `MailFromCity2` | Tonnes; unused by this project |

## Known data characteristics (verified 2026-08-31, not assumed)

- 65,166 rows, 191 distinct city names, covering **2015 to 2026-05**
  (most recent complete month at retrieval time — official statistics lag
  roughly 2–3 months behind the current calendar month, which is why the
  engine's default weighting window is the latest available rolling 12
  months, not "the current 12 months").
- Mumbai appears under three separate names: `MUMBAI` (7,351 rows, the
  historically dominant/canonical entry), `MUMBAI (MUMBAI)` (336 rows),
  and `MUMBAI (NAVI MUMBAI)` (165 rows, a genuinely different airport).
  `index_engine.city_mapping` maps IATA `BOM` to plain `MUMBAI` only —
  the other two are deliberately left unmapped rather than fuzzy-merged.
- No airline breakdown — this file is already route-level, so no
  airline-aggregation step is needed before computing weights.

## Reproducing / updating this file

Re-run the `curl` command above to refresh with the latest upstream data.
This file is committed to the repo (not `.gitignore`d) because it is
real, ODbL-licensed, and small enough (~3.8 MB) to version — there is no
licensing reason to exclude it, unlike a scraped-airfare dataset would be.
