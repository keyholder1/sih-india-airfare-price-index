import { useEffect, useRef, useState, type FormEvent } from "react";
import clsx from "clsx";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { useScrapeJob } from "../../hooks/useScrapeJob";
import { formatIndex, formatPeriod, formatINR } from "../../utils/format";

const STEPS: { key: string; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "scraping", label: "Scraping (SerpApi)" },
  { key: "validating", label: "Data Quality" },
  { key: "indexing", label: "Index Engine" },
  { key: "done", label: "Done" },
];

function stepIndex(status: string): number {
  const i = STEPS.findIndex((s) => s.key === status);
  return i === -1 ? 0 : i;
}

/** Section 8: a real, live, user-triggered run of the whole pipeline for
 * one route pair -- scrape (SerpApi) -> Data Quality -> Postgres ->
 * Index Engine -- not a simulation, not pre-computed. If the route
 * already has previously-recorded real data, the fresh SerpApi call is
 * skipped and that data is reused instead (see result.from_cache). */
export function RouteLookupSection({ onComplete }: { onComplete?: () => void }) {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const { job, error, retrying, isRunning, start, reset } = useScrapeJob();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const o = origin.trim().toUpperCase();
    const d = destination.trim().toUpperCase();
    if (o.length !== 3 || d.length !== 3) return;
    if (o === d) {
      setFormError("Origin and destination must be different routes.");
      return;
    }
    setFormError(null);
    start(o, d);
  }

  const result = job?.result ?? null;
  const failed = job?.status === "failed";
  const done = job?.status === "done";

  // The pipeline persists new/updated data straight to Postgres -- notify
  // the rest of the dashboard once per completed job so National Index,
  // Route Intelligence, Data Quality and the Forecast section refetch and
  // reflect it, instead of staying frozen at whatever loaded on page
  // mount. Guarded by job id so this fires once per job, not on every
  // re-render while status stays "done".
  const notifiedJobId = useRef<string | null>(null);
  useEffect(() => {
    if (done && job && notifiedJobId.current !== job.id) {
      notifiedJobId.current = job.id;
      onComplete?.();
    }
  }, [done, job, onComplete]);

  return (
    <section className="scroll-mt-20">
      <SectionHeader
        index={8}
        title="Try it yourself: run the real pipeline for any route"
        description="Enter two IATA airport codes. This makes a real, live call to SerpApi/Google Flights, runs it through Data Quality, persists it to Postgres, and recomputes the national index -- the same pipeline the rest of this dashboard uses, triggered by you, right now."
      />

      <Panel className="p-5">
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="rl-origin" className="mb-1 block text-[0.66rem] uppercase tracking-wide text-ink-faint">
              Origin
            </label>
            <input
              id="rl-origin"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              placeholder="BLR"
              maxLength={3}
              disabled={isRunning}
              className="w-20 rounded-md border border-hairline-strong bg-surface px-2.5 py-1.5 text-sm font-semibold uppercase tabular tracking-wide text-ink focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50"
            />
          </div>
          <span className="pb-2 text-ink-faint">&rarr;</span>
          <div>
            <label htmlFor="rl-dest" className="mb-1 block text-[0.66rem] uppercase tracking-wide text-ink-faint">
              Destination
            </label>
            <input
              id="rl-dest"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="DEL"
              maxLength={3}
              disabled={isRunning}
              className="w-20 rounded-md border border-hairline-strong bg-surface px-2.5 py-1.5 text-sm font-semibold uppercase tabular tracking-wide text-ink focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50"
            />
          </div>
          <button
            type="submit"
            disabled={isRunning || origin.trim().length !== 3 || destination.trim().length !== 3}
            className="rounded-md bg-brand px-4 py-1.5 text-sm font-semibold text-ink-inverse transition-colors hover:bg-brand-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isRunning ? "Running…" : "Run pipeline"}
          </button>
          {job && (
            <button
              type="button"
              onClick={reset}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-ink-faint transition-colors hover:bg-surface-sunken hover:text-ink"
            >
              {isRunning ? "Cancel" : "Clear"}
            </button>
          )}
        </form>

        {formError && (
          <p className="mt-4 rounded-md border border-rise/30 bg-rise-wash px-3 py-2 text-sm text-rise">{formError}</p>
        )}

        {error && (
          <p className="mt-4 rounded-md border border-rise/30 bg-rise-wash px-3 py-2 text-sm text-rise">{error}</p>
        )}

        {retrying && !error && (
          <p className="mt-4 rounded-md border border-synth-border bg-synth-wash px-3 py-2 text-sm text-synth">
            Connection hiccup -- retrying...
          </p>
        )}

        {job && (
          <div className="mt-5 border-t border-hairline pt-4">
            <div className="flex flex-wrap items-center gap-2">
              {STEPS.map((s, i) => (
                <span
                  key={s.key}
                  className={clsx(
                    "rounded-full border px-2.5 py-1 text-[0.66rem] font-semibold uppercase tracking-wide",
                    failed && i === stepIndex(job.status)
                      ? "border-rise/30 bg-rise-wash text-rise"
                      : i < stepIndex(job.status) || done
                        ? "border-fall/30 bg-fall-wash text-fall"
                        : i === stepIndex(job.status)
                          ? "border-brand/30 bg-brand-wash text-brand"
                          : "border-hairline-strong bg-surface-sunken text-ink-faint"
                  )}
                >
                  {s.label}
                </span>
              ))}
            </div>
            <p className="mt-3 text-sm text-ink-muted">{job.message}</p>
            {failed && job.error && <p className="mt-1 text-xs text-rise">{job.error}</p>}
          </div>
        )}

        {done && result && (
          <div className="mt-5 grid grid-cols-1 gap-4 border-t border-hairline pt-4 sm:grid-cols-2">
            <div>
              <p className="eyebrow">{result.route}</p>
              <p className="mt-1 text-xs text-ink-faint">
                {result.from_cache
                  ? "Reused previously-recorded real data for this route — no fresh SerpApi call was needed."
                  : "Fresh live SerpApi call, just now."}
              </p>
              <dl className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Route status</dt>
                  <dd className="mt-0.5 text-sm font-semibold text-ink">{result.route_status}</dd>
                </div>
                <div>
                  <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Route index</dt>
                  <dd className="mt-0.5 text-sm font-semibold tabular text-ink">{formatIndex(result.route_index)}</dd>
                </div>
                {!result.from_cache && (
                  <>
                    <div>
                      <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Raw collected</dt>
                      <dd className="mt-0.5 text-sm font-semibold tabular text-ink">{result.raw_observations_collected}</dd>
                    </div>
                    <div>
                      <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Quality grade</dt>
                      <dd className="mt-0.5 text-sm font-semibold text-ink">{result.quality_grade}</dd>
                    </div>
                  </>
                )}
              </dl>
            </div>
            <div>
              <p className="eyebrow">Updated national index</p>
              <p className="mt-1 text-xs text-ink-faint">
                Recomputed across all {result.updated_routes_total} tracked routes, {formatPeriod(result.updated_base_period)} = 100
              </p>
              <div className="mt-3 flex items-baseline gap-3">
                <span className="text-3xl font-semibold tabular text-ink">{formatIndex(result.updated_national_index)}</span>
                <span className="text-xs text-ink-faint">as of {formatPeriod(result.updated_current_period)}</span>
              </div>
              <p className="mt-1 text-[0.68rem] text-ink-faint">
                data_source: {result.updated_national_index_data_source} &middot; {result.updated_routes_covered}/{result.updated_routes_total} routes covered
              </p>
            </div>
          </div>
        )}

        {done && result && result.fare_count > 0 && (
          <div className="mt-5 border-t border-hairline pt-4">
            <p className="eyebrow">Actual fares collected for {result.route}</p>
            <p className="mt-1 text-xs text-ink-faint">
              {result.fare_count} real fare{result.fare_count === 1 ? "" : "s"} in Postgres for this route
              {result.route_base_period_fare != null && result.route_period_fare != null && (
                <>
                  {" "}&middot; base period avg {formatINR(result.route_base_period_fare)} &rarr; current period avg{" "}
                  {formatINR(result.route_period_fare)}
                </>
              )}
            </p>

            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Cheapest</dt>
                <dd className="mt-0.5 text-sm font-semibold tabular text-ink">{formatINR(result.fare_min)}</dd>
              </div>
              <div>
                <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Median</dt>
                <dd className="mt-0.5 text-sm font-semibold tabular text-ink">{formatINR(result.fare_median)}</dd>
              </div>
              <div>
                <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Mean</dt>
                <dd className="mt-0.5 text-sm font-semibold tabular text-ink">{formatINR(result.fare_mean)}</dd>
              </div>
              <div>
                <dt className="text-[0.64rem] uppercase tracking-wide text-ink-faint">Most expensive</dt>
                <dd className="mt-0.5 text-sm font-semibold tabular text-ink">{formatINR(result.fare_max)}</dd>
              </div>
            </dl>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-sm">
                <thead>
                  <tr className="text-[0.64rem] uppercase tracking-wide text-ink-faint">
                    <th className="pb-1.5 pr-3 font-medium">Airline</th>
                    <th className="pb-1.5 pr-3 font-medium">Flight date</th>
                    <th className="pb-1.5 pr-3 font-medium">Booked</th>
                    <th className="pb-1.5 pr-3 font-medium">Source</th>
                    <th className="pb-1.5 text-right font-medium">Fare</th>
                  </tr>
                </thead>
                <tbody>
                  {result.sample_fares.map((f, i) => (
                    <tr key={i} className="border-t border-hairline">
                      <td className="py-1.5 pr-3 text-ink">{f.airline ?? "—"}</td>
                      <td className="py-1.5 pr-3 tabular text-ink-muted">{f.flight_date ?? "—"}</td>
                      <td className="py-1.5 pr-3 tabular text-ink-muted">{f.booking_date ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-ink-muted">{f.source ?? "—"}</td>
                      <td className="py-1.5 text-right font-semibold tabular text-ink">{formatINR(f.total_fare)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.fare_count > result.sample_fares.length && (
                <p className="mt-2 text-[0.68rem] text-ink-faint">
                  Showing the {result.sample_fares.length} cheapest of {result.fare_count} real fares on file for this route.
                </p>
              )}
            </div>
          </div>
        )}
      </Panel>
    </section>
  );
}
