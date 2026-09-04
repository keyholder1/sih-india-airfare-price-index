import type { PriceIndex } from "../../types";
import { Panel } from "../primitives/Panel";
import { StatValue } from "../primitives/StatValue";
import { DeltaPill } from "../primitives/DeltaPill";
import { InfoHint } from "../primitives/InfoHint";
import {
  formatFractionPct,
  formatIndex,
  formatInt,
  formatPeriod,
} from "../../utils/format";

interface IndexHeroProps {
  priceIndex: PriceIndex;
  trafficWeightCoverage: number | null;
}

function MetaItem({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <dt className="text-[0.68rem] uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular text-ink">{value}</dd>
      {sub && <p className="mt-0.5 text-[0.65rem] text-ink-faint">{sub}</p>}
    </div>
  );
}

export function IndexHero({ priceIndex: pi, trafficWeightCoverage }: IndexHeroProps) {
  return (
    <Panel className="flex h-full flex-col justify-between p-6">
      <div>
        <p className="eyebrow">National Airfare Price Index</p>
        <div className="mt-3 flex items-end gap-4">
          <StatValue value={pi.national_index} format={(v) => formatIndex(v)} size="hero" />
          <span className="flex items-center gap-1 pb-2 text-sm text-ink-faint">
            {formatPeriod(pi.base_period)} = 100
            <InfoHint
              align="left"
              text={`The "base period" is fixed at ${formatPeriod(
                pi.base_period
              )} and pinned to 100 -- every other month's index is that month's average fare relative to this one. 122 means "22% more expensive than the base period," not a rupee amount.`}
            />
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2.5">
          <span className="inline-flex items-center gap-1">
            <DeltaPill value={pi.mom_change_pct} label="MoM" />
            <InfoHint text="Month-over-month: how much the national index changed vs. the immediately previous month." />
          </span>
          <span className="inline-flex items-center gap-1">
            <DeltaPill
              value={pi.yoy_change_pct}
              label="YoY"
              nullText="n/a · needs 12 mo"
            />
            <InfoHint text="Year-over-year: how much the index changed vs. the same month last year. Needs 12 months of history to compute -- shown honestly as unavailable, not zero, until then." />
          </span>
          <span className="text-xs text-ink-faint">
            vs. {formatPeriod(pi.current_period)}
          </span>
        </div>
      </div>

      <dl className="mt-8 grid grid-cols-2 gap-4 border-t border-hairline pt-4 sm:grid-cols-4">
        <MetaItem
          label="Routes covered"
          value={`${pi.routes_covered}/${pi.routes_total}`}
          sub="tracked routes reporting"
        />
        <MetaItem label="Observations used" value={formatInt(pi.observations_used)} />
        <MetaItem
          label="Route coverage"
          value={formatFractionPct(pi.coverage_rate)}
          sub="of tracked routes, not national traffic"
        />
        <MetaItem
          label="Traffic coverage"
          value={formatFractionPct(trafficWeightCoverage)}
          sub="share of national domestic pax"
        />
      </dl>
    </Panel>
  );
}
