import { useMemo, useState } from "react";
import type { AnalyticsResult, IndexTimeseriesPoint } from "../../types";
import { buildContributionBreakdown } from "../../utils/contributions";
import {
  formatIndex,
  formatPeriod,
  formatSignedPct,
  shiftPeriod,
} from "../../utils/format";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { DeltaPill } from "../primitives/DeltaPill";
import { ContributionDivergingChart } from "../charts/ContributionDivergingChart";

interface IndexContributionSectionProps {
  analytics: AnalyticsResult;
  timeseries: IndexTimeseriesPoint[] | null;
  selectedRoute: string | null;
  onRouteSelect: (route: string | null) => void;
}

const DEFAULT_VISIBLE = 6;

export function IndexContributionSection({
  analytics,
  timeseries,
  selectedRoute,
  onRouteSelect,
}: IndexContributionSectionProps) {
  const [expanded, setExpanded] = useState(false);

  const breakdown = useMemo(
    () => buildContributionBreakdown(analytics),
    [analytics],
  );

  const pi = analytics.price_index;
  const prevPeriod = shiftPeriod(pi.current_period, -1);
  const prevPoint = timeseries?.find((p) => p.period === prevPeriod) ?? null;

  const mom = pi.mom_change_pct;
  const movementWord =
    mom == null ? "changed" : mom < 0 ? "fell" : mom > 0 ? "rose" : "held flat";

  const total = breakdown.ranked.length;
  const canExpand = total > DEFAULT_VISIBLE;
  const visibleRows =
    expanded || !canExpand
      ? breakdown.ranked
      : breakdown.ranked.slice(0, DEFAULT_VISIBLE);

  const posCount = breakdown.positive.length;
  const negCount = breakdown.negative.length;

  return (
    <section>
      <SectionHeader
        index={2}
        title="Why did the index move?"
        description="Which routes contributed most to the latest movement — and by how much."
      />

      <Panel className="p-6">
        {/* movement headline */}
        <p className="eyebrow">National index movement</p>
        <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-2">
          <div className="flex items-baseline gap-2 text-lg tabular text-ink-faint">
            {prevPoint?.national_index != null && (
              <>
                <span>{formatIndex(prevPoint.national_index)}</span>
                <span aria-hidden>→</span>
              </>
            )}
            <span className="text-stat-num font-semibold text-ink">
              {formatIndex(pi.national_index)}
            </span>
          </div>
          <DeltaPill value={mom} label="MoM" />
          <span className="pb-1 text-xs text-ink-faint">
            {formatPeriod(prevPeriod)} → {formatPeriod(pi.current_period)}
          </span>
        </div>

        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-muted">
          The national index {movementWord}{" "}
          {mom != null && (
            <span className="font-medium text-ink">{formatSignedPct(mom)}</span>
          )}{" "}
          from {formatPeriod(prevPeriod)}. That movement decomposes exactly into
          the per-route contributions below, ordered by how much each route moved
          the index.
        </p>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-faint">
          <span>
            <span className="font-semibold text-rise">{posCount}</span> routes
            pushed it up
          </span>
          <span>
            <span className="font-semibold text-fall">{negCount}</span> routes
            pulled it down
          </span>
          <span>
            {analytics.price_index.routes_covered} of{" "}
            {analytics.price_index.routes_total} routes contributing
          </span>
        </div>

        {/* diverging chart */}
        <div className="mt-6">
          <ContributionDivergingChart
            rows={visibleRows}
            maxAbs={breakdown.maxAbs}
            selectedRoute={selectedRoute}
            onRouteSelect={onRouteSelect}
          />
        </div>

        {canExpand && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-3 text-xs font-semibold text-accent transition-colors hover:text-brand focus:outline-none focus-visible:underline"
          >
            {expanded ? "Show top contributors" : `View all ${total} contributors`}
          </button>
        )}

        {/* methodology note: contribution ≠ cause */}
        <div className="mt-6 space-y-2 border-t border-hairline pt-4">
          <p className="text-xs leading-relaxed text-ink-muted">
            <span className="font-semibold text-ink">Route contribution</span> is
            a route&apos;s month-over-month price change weighted by its share of
            national passenger traffic (DGCA-derived). Contributions sum exactly
            to the index&apos;s point change — this is a decomposition, computed
            by the statistics engine.
          </p>
          <p className="text-xs leading-relaxed text-ink-faint">
            It shows{" "}
            <span className="font-medium text-ink-muted">
              statistical contribution
            </span>
            , not the cause of any price change. This dashboard does not infer
            why fares moved.
          </p>
        </div>
      </Panel>
    </section>
  );
}
