import { useForecast } from "../../hooks/useForecast";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { StatValue } from "../primitives/StatValue";
import { formatIndex, formatPeriod, formatSignedPct } from "../../utils/format";

/** Section 7: one-period-ahead national forecast (naive baseline) and a
 * comparison against MoSPI's official CPI Airfare sub-index, where the
 * two series actually overlap. Both are new capabilities (PR #7) with no
 * prior frontend presence at all. */
export function ForecastSection() {
  const forecast = useForecast();

  return (
    <section className="scroll-mt-20">
      <SectionHeader
        index={7}
        title="Forecast & CPI benchmark"
        description="A one-period-ahead baseline forecast, and how our index compares to MoSPI's official CPI Airfare sub-index over any overlapping months."
      />

      {forecast.loading && <p className="text-sm text-ink-faint">Loading forecast…</p>}

      {forecast.data && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Panel className="p-5">
            <p className="eyebrow">National forecast</p>
            {forecast.data.national_forecast.status !== "OK" ? (
              <p className="mt-3 text-sm text-ink-faint">
                {forecast.data.national_forecast.notes ?? `Status: ${forecast.data.national_forecast.status}`}
              </p>
            ) : (
              <>
                <div className="mt-3 flex items-baseline gap-3">
                  <StatValue value={forecast.data.national_forecast.forecast_value} format={(v) => formatIndex(v)} size="stat" />
                  <span className="text-sm text-ink-faint">
                    for {formatPeriod(forecast.data.national_forecast.forecast_period)}
                  </span>
                </div>
                <p className="mt-2 text-xs text-ink-faint">
                  {forecast.data.national_forecast.model_used} baseline · trained on{" "}
                  {forecast.data.national_forecast.training_period.map(formatPeriod).join(", ")} (
                  {forecast.data.national_forecast.data_points_used} points)
                </p>
                {forecast.data.national_forecast.lower_bound != null && forecast.data.national_forecast.upper_bound != null && (
                  <p className="mt-1 text-xs tabular text-ink-faint">
                    Range: {formatIndex(forecast.data.national_forecast.lower_bound)} – {formatIndex(forecast.data.national_forecast.upper_bound)}
                  </p>
                )}
                {forecast.data.national_forecast.notes && (
                  <p className="mt-2 text-xs text-ink-faint">{forecast.data.national_forecast.notes}</p>
                )}
              </>
            )}
            <p className="mt-4 text-xs font-medium text-synth">
              {forecast.data.national_forecast.is_synthetic_data ? "Synthetic demonstration data." : "Real scraped data."}{" "}
              A naive baseline forecast, not a validated economic model.
            </p>
          </Panel>

          <Panel className="p-5">
            <p className="eyebrow">MoSPI CPI Airfare benchmark</p>
            {!forecast.data.cpi_benchmark || forecast.data.cpi_benchmark.status !== "OK" ? (
              <p className="mt-3 text-sm text-ink-faint">
                {forecast.data.cpi_benchmark?.notes ?? "No overlapping period with MoSPI's published series yet."}
              </p>
            ) : (
              <>
                <div className="mt-3 grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-ink-faint">Overlap</p>
                    <p className="tabular text-sm font-semibold text-ink">
                      {formatPeriod(forecast.data.cpi_benchmark.overlap_start ?? "")} –{" "}
                      {formatPeriod(forecast.data.cpi_benchmark.overlap_end ?? "")}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-ink-faint">MoM correlation</p>
                    <p className="tabular text-sm font-semibold text-ink">
                      {forecast.data.cpi_benchmark.mom_correlation == null ? "n/a" : forecast.data.cpi_benchmark.mom_correlation.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-ink-faint">Mean abs. MoM diff</p>
                    <p className="tabular text-sm font-semibold text-ink">
                      {forecast.data.cpi_benchmark.mean_absolute_mom_difference_pct_points == null
                        ? "n/a"
                        : `${forecast.data.cpi_benchmark.mean_absolute_mom_difference_pct_points.toFixed(2)} pt`}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-ink-faint">Periods compared</p>
                    <p className="tabular text-sm font-semibold text-ink">{forecast.data.cpi_benchmark.overlap_period_count}</p>
                  </div>
                </div>

                {forecast.data.cpi_benchmark.comparisons.length > 0 && (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full min-w-[380px] text-xs">
                      <thead>
                        <tr className="border-b border-hairline text-left uppercase tracking-wide text-ink-faint">
                          <th className="pb-1.5 font-semibold">Period</th>
                          <th className="pb-1.5 text-right font-semibold">Our MoM</th>
                          <th className="pb-1.5 text-right font-semibold">MoSPI MoM</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-hairline/70">
                        {forecast.data.cpi_benchmark.comparisons.map((c) => (
                          <tr key={c.period}>
                            <td className="py-1.5 tabular text-ink">{formatPeriod(c.period)}</td>
                            <td className="py-1.5 text-right tabular text-ink-muted">{formatSignedPct(c.our_mom_pct)}</td>
                            <td className="py-1.5 text-right tabular text-ink-muted">{formatSignedPct(c.mospi_mom_pct)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
            <p className="mt-4 text-xs text-ink-faint">
              MoSPI = Ministry of Statistics and Programme Implementation's official CPI Airfare sub-index -- an
              external, independently published reference, not our own data.
            </p>
          </Panel>
        </div>
      )}
    </section>
  );
}
