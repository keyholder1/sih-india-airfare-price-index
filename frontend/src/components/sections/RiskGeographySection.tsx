import { useState } from "react";
import clsx from "clsx";
import type { AnalyticsResult } from "../../types";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { InflationHeatmap } from "../charts/InflationHeatmap";
import { BookingHorizonChart } from "../charts/BookingHorizonChart";

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
            <p className="eyebrow">Inflation matrix</p>
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
          <p className="eyebrow">Booking-horizon volatility (national)</p>
          <p className="mt-1 text-xs text-ink-faint">
            Coefficient of variation of fares within each booking window -- higher means less predictable, not necessarily more expensive.
          </p>
          <div className="mt-4">
            <BookingHorizonChart data={analytics.volatility.booking_horizon_volatility} />
          </div>
        </Panel>
      </div>
    </section>
  );
}
