import type { PriceIndex } from "../../types";
import { Panel } from "../primitives/Panel";
import { StatValue } from "../primitives/StatValue";
import { DeltaPill } from "../primitives/DeltaPill";
import {
  formatFractionPct,
  formatIndex,
  formatInt,
  formatPeriod,
} from "../../utils/format";

interface IndexHeroProps {
  priceIndex: PriceIndex;
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[0.68rem] uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular text-ink">{value}</dd>
    </div>
  );
}

export function IndexHero({ priceIndex: pi }: IndexHeroProps) {
  return (
    <Panel className="flex h-full flex-col justify-between p-6">
      <div>
        <p className="eyebrow">National Airfare Price Index</p>
        <div className="mt-3 flex items-end gap-4">
          <StatValue value={pi.national_index} format={(v) => formatIndex(v)} size="hero" />
          <span className="pb-2 text-sm text-ink-faint">
            {formatPeriod(pi.base_period)} = 100
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2.5">
          <DeltaPill value={pi.mom_change_pct} label="MoM" />
          <DeltaPill
            value={pi.yoy_change_pct}
            label="YoY"
            nullText="n/a · needs 12 mo"
          />
          <span className="text-xs text-ink-faint">
            vs. {formatPeriod(pi.current_period)}
          </span>
        </div>
      </div>

      <dl className="mt-8 grid grid-cols-3 gap-4 border-t border-hairline pt-4">
        <MetaItem
          label="Routes covered"
          value={`${pi.routes_covered}/${pi.routes_total}`}
        />
        <MetaItem label="Observations used" value={formatInt(pi.observations_used)} />
        <MetaItem label="Weight coverage" value={formatFractionPct(pi.coverage_rate)} />
      </dl>
    </Panel>
  );
}
