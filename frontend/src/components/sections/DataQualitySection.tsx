import clsx from "clsx";
import type { DataQualityResult } from "../../types";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { StatValue } from "../primitives/StatValue";
import { InfoHint } from "../primitives/InfoHint";
import { formatFractionPct, formatInt } from "../../utils/format";

interface DataQualitySectionProps {
  quality: DataQualityResult | null;
  loading: boolean;
}

// data_quality's own PROTOTYPE grade vocabulary (see
// src/data_quality/config.py's QUALITY_GRADE_BANDS) -- this endpoint
// returns the engine's raw grade word, not a letter grade.
const GRADE_TONE: Record<string, string> = {
  EXCELLENT: "text-fall bg-fall-wash border-fall/20",
  GOOD: "text-fall bg-fall-wash border-fall/20",
  WARNING: "text-synth bg-synth-wash border-synth-border",
  POOR: "text-rise bg-rise-wash border-rise/20",
};

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "HEALTHY"
      ? "text-fall bg-fall-wash border-fall/20"
      : status === "DEGRADED"
        ? "text-synth bg-synth-wash border-synth-border"
        : status === "FAILED"
          ? "text-rise bg-rise-wash border-rise/20"
          : "text-ink-faint bg-surface-sunken border-hairline";
  return (
    <span className={clsx("rounded-full border px-2 py-0.5 text-[0.62rem] font-semibold uppercase tracking-wide", tone)}>
      {status}
    </span>
  );
}

export function DataQualitySection({ quality, loading }: DataQualitySectionProps) {
  return (
    <section className="scroll-mt-20">
      <SectionHeader
        index={4}
        title="Data quality"
        description="Every rejected or flagged observation is accounted for with a reason -- nothing is silently dropped."
      />

      {loading && <p className="text-sm text-ink-faint">Loading data quality report…</p>}

      {quality && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Panel className="p-5">
            <p className="eyebrow flex items-center gap-1">
              Overall quality
              <InfoHint
                align="left"
                text="A weighted blend of completeness, validity, duplicate rate, schema compliance and source success -- a transparent formula (src/data_quality/scoring.py), not a black box. A low score here is the validator doing its job on real messy data, not a sign the index itself is wrong: flagged/rejected rows never silently disappear."
              />
            </p>
            <div className="mt-3 flex items-center gap-4">
              <div>
                <StatValue value={quality.quality_score} format={(v) => (v == null ? "—" : `${v.toFixed(1)}%`)} size="stat" />
                <p className="mt-0.5 text-xs text-ink-faint">quality score</p>
              </div>
              <span
                className={clsx(
                  "rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide",
                  GRADE_TONE[quality.quality_grade] ?? "text-ink-faint bg-surface-sunken border-hairline",
                )}
              >
                {quality.quality_grade}
              </span>
            </div>

            <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <div>
                <dt className="text-xs text-ink-faint">Records received</dt>
                <dd className="tabular font-semibold text-ink">{formatInt(quality.records_received)}</dd>
              </div>
              <div>
                <dt className="flex items-center gap-1 text-xs text-ink-faint">
                  Valid
                  <InfoHint text="Passed every check with zero caveats -- reaches the index pipeline with no asterisk." />
                </dt>
                <dd className="tabular font-semibold text-fall">{formatInt(quality.records_valid)}</dd>
              </div>
              <div>
                <dt className="flex items-center gap-1 text-xs text-ink-faint">
                  Flagged
                  <InfoHint text="Structurally fine and STILL used in the index -- just worth a second look (e.g. an unusually high fare, or a field this source doesn't provide). Flagged is not rejected." />
                </dt>
                <dd className="tabular font-semibold text-synth">{formatInt(quality.records_flagged)}</dd>
              </div>
              <div>
                <dt className="flex items-center gap-1 text-xs text-ink-faint">
                  Rejected
                  <InfoHint text="Excluded from the index entirely, each with exactly one stated reason (see Rejection reasons below) -- never silently dropped." />
                </dt>
                <dd className="tabular font-semibold text-rise">{formatInt(quality.records_rejected)}</dd>
              </div>
              <div>
                <dt className="flex items-center gap-1 text-xs text-ink-faint">
                  Completeness
                  <InfoHint text="Share of records with every required field present (route, dates, fare, currency, ...) -- about the record's shape, not whether its values look right." />
                </dt>
                <dd className="tabular text-ink">{formatFractionPct(quality.completeness_rate)}</dd>
              </div>
              <div>
                <dt className="flex items-center gap-1 text-xs text-ink-faint">
                  Validity
                  <InfoHint text="Share of records that are fully Valid (no flags at all) -- stricter than completeness, since a record can be complete and still get flagged." />
                </dt>
                <dd className="tabular text-ink">{formatFractionPct(quality.validity_rate)}</dd>
              </div>
            </dl>

            {Object.keys(quality.rejection_reasons).length > 0 && (
              <div className="mt-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Rejection reasons</p>
                <ul className="mt-2 space-y-1.5">
                  {Object.entries(quality.rejection_reasons).map(([reason, count]) => (
                    <li key={reason} className="flex items-center justify-between text-xs">
                      <span className="text-ink-muted">{reason.replace(/_/g, " ").toLowerCase()}</span>
                      <span className="tabular font-semibold text-ink">{count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>

          <Panel className="p-5">
            <p className="eyebrow">Source health</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[420px] text-sm">
                <thead>
                  <tr className="border-b border-hairline text-left text-[0.62rem] uppercase tracking-wide text-ink-faint">
                    <th className="pb-2 font-semibold">Source</th>
                    <th className="pb-2 text-right font-semibold">Status</th>
                    <th className="pb-2 text-right font-semibold">Received</th>
                    <th className="pb-2 text-right font-semibold">Valid rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/70">
                  {quality.source_health.map((s) => (
                    <tr key={s.source}>
                      <td className="py-2 font-medium text-ink">{s.source}</td>
                      <td className="py-2 text-right"><StatusPill status={s.status} /></td>
                      <td className="py-2 text-right tabular text-ink-muted">{formatInt(s.observations_received)}</td>
                      <td className="py-2 text-right tabular text-ink">{formatFractionPct(s.observation_validity_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="mt-5 eyebrow">Route health</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[420px] text-sm">
                <thead>
                  <tr className="border-b border-hairline text-left text-[0.62rem] uppercase tracking-wide text-ink-faint">
                    <th className="pb-2 font-semibold">Route</th>
                    <th className="pb-2 text-right font-semibold">Total</th>
                    <th className="pb-2 text-right font-semibold">Valid</th>
                    <th className="pb-2 text-right font-semibold">Quality rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/70">
                  {quality.route_health.map((r) => (
                    <tr key={r.route}>
                      <td className="py-2 font-medium text-ink">{r.origin} → {r.destination}</td>
                      <td className="py-2 text-right tabular text-ink-muted">{formatInt(r.observations_total)}</td>
                      <td className="py-2 text-right tabular text-ink-muted">{formatInt(r.observations_valid)}</td>
                      <td className="py-2 text-right tabular text-ink">{formatFractionPct(r.route_quality_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </section>
  );
}
