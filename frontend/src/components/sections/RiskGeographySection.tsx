import { useState } from "react";
import clsx from "clsx";
import type { AnalyticsResult } from "../../types";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { InflationHeatmap } from "../charts/InflationHeatmap";
import { BookingHorizonChart } from "../charts/BookingHorizonChart";
import { InfoHint } from "../primitives/InfoHint";
import { useNaturalEvents } from "../../hooks/useNaturalEvents";
import { routeLabel } from "../../utils/format";

interface RiskGeographySectionProps {
  analytics: AnalyticsResult;
}

/** Section 5: the origin x destination inflation matrix
 * ("heatmap-ready, missing != zero" per docs/sih_pitch.md) and
 * booking-horizon volatility -- a second, genuinely different signal
 * from the price index (a route can be flat and still unpredictable
 * booking to booking). Neither is shown anywhere else on the dashboard. */
export function RiskGeographySection({ analytics }: RiskGeographySectionProps) {
  const [metric, setMetric] = useState<"mom" | "yoy">("mom");
  const matrix = metric === "mom" ? analytics.inflation_matrix_mom : analytics.inflation_matrix_yoy;
  const naturalEvents = useNaturalEvents();

  return (
    <section className="scroll-mt-20">
      <SectionHeader
        index={5}
        title="Route inflation heatmap & booking-horizon volatility"
        description="Where fares are actually moving, and how unstable a route is booking to booking -- independent of whether the route index itself moved."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="eyebrow flex items-center gap-1">
              Inflation matrix
              <InfoHint
                align="left"
                text="Origin (row) → destination (column), colour = % fare change. A blank cell means no data for that pair, never 0% -- missing is not the same as flat."
              />
            </p>
            <div role="radiogroup" aria-label="Matrix metric" className="inline-flex rounded-lg border border-hairline bg-surface-sunken p-0.5">
              {(["mom", "yoy"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={metric === m}
                  onClick={() => setMetric(m)}
                  className={clsx(
                    "rounded-md px-2.5 py-1 text-xs font-semibold transition-colors",
                    metric === m ? "bg-surface text-ink shadow-sm" : "text-ink-faint hover:text-ink-muted",
                  )}
                >
                  {m.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4">
            {matrix ? (
              <InflationHeatmap matrix={matrix} metric={metric === "mom" ? "MoM" : "YoY"} />
            ) : (
              <p className="py-8 text-center text-sm text-ink-faint">Heatmap not available from this data source.</p>
            )}
          </div>
        </Panel>

        <Panel className="p-5">
          <p className="eyebrow flex items-center gap-1">
            Booking-horizon volatility (national)
            <InfoHint
              align="left"
              text="“Coefficient of variation” = standard deviation ÷ mean fare within one booking window (e.g. ≤30 days out vs. 60+ days out). It measures how much fares swing around, not how expensive they are -- a high bar means unpredictable pricing, not a price spike."
            />
          </p>
          <p className="mt-1 text-xs text-ink-faint">
            Coefficient of variation of fares within each booking window -- higher means less predictable, not necessarily more expensive.
          </p>
          <div className="mt-4">
            <BookingHorizonChart data={analytics.volatility.booking_horizon_volatility} />
          </div>
        </Panel>
      </div>

      {/* Recent real NASA EONET natural events tied to a significant
         route movement -- deliberately not every event near India, only
         ones actually relevant to a route worth explaining. Contextual
         only, never a claimed cause. See docs/eonet_context.md. */}
      {naturalEvents.data && naturalEvents.data.events.length > 0 && (
        <Panel className="mt-5 p-5">
          <p className="eyebrow">Recent natural events (potential route context)</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-[0.62rem] uppercase tracking-wide text-ink-faint">
                  <th className="pb-2 font-semibold">Event</th>
                  <th className="pb-2 font-semibold">Route potentially affected</th>
                  <th className="pb-2 text-right font-semibold">Date</th>
                  <th className="pb-2 text-right font-semibold">Match</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/70">
                {naturalEvents.data.events.map((ev) => (
                  <tr key={ev.event_id}>
                    <td className="py-2 text-ink">
                      <span aria-hidden>{ev.category_emoji}</span> {ev.category_label}: {ev.title}
                    </td>
                    <td className="py-2 text-ink-muted">{routeLabel(ev.route)}</td>
                    <td className="py-2 text-right tabular text-ink-muted">{ev.event_date.slice(0, 10)}</td>
                    <td className="py-2 text-right tabular text-ink-faint">{(ev.relevance_score * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[0.68rem] italic text-ink-faint">
            Real NASA EONET events, geographically and temporally associated with a route that had a significant fare movement --
            contextual only, never a confirmed cause. Never used to compute the index.
          </p>
        </Panel>
      )}
    </section>
  );
}
