# Raw scraper output

One `.jsonl` file per scrape run, named `<run_id>.jsonl` (see
`scraper.storage.write_raw_run`). This is exactly what the scraper
collected — before `data_quality.validate_fare_batch` has looked at any
of it. Never point `AirfarePriceIndex` at this directory directly; use
`data/validated/fares/` instead (see `docs/scraper.md` §7).

Every record here that came from `scraper.mock_source.MockFareSource`
carries `"is_mock": true` — treat any file containing such records as
demonstration data, not real airfares.
