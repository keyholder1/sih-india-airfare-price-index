# Validated fare observations

One `.jsonl` file per run, named `<run_id>.jsonl` (see
`scraper.storage.write_validated_run`), containing the
`data_quality.DataQualityResult.valid_observations` for that run — VALID
and FLAGGED records only, never REJECTED. This is the tree
`AirfarePriceIndex.calculate(...)` should actually read from. See
`docs/scraper.md` §7 and `docs/data_quality.md` for why REJECTED
observations must never reach here.
