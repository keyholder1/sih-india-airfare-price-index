# Scraper run reports

One `.json` file per run, named `<run_id>.json` (see
`scraper.storage.write_run_report`) — the structured
`scraper.models.ScrapeRunReport`: routes requested/successful/failed,
per-source observation counts, and a failure-reason breakdown. Nothing
here is hidden or averaged away; see `docs/scraper.md` §8.
