import clsx from "clsx";
import type { ContributionRow } from "../../utils/contributions";
import {
  formatFractionPct,
  formatIndex,
  formatPoints,
  formatSignedPct,
  routeLabel,
} from "../../utils/format";

interface ContributionDivergingChartProps {
  rows: ContributionRow[];
  /** largest absolute contribution across the full set — bars scale to this */
  maxAbs: number;
  selectedRoute: string | null;
  onRouteSelect: (route: string | null) => void;
}

/** half-track percentage for a bar, with a visible minimum */
function barPercent(value: number, maxAbs: number): number {
  if (maxAbs <= 0) return 0;
  return Math.max((Math.abs(value) / maxAbs) * 50, 1.6);
}

function ContributionTooltip({ row }: { row: ContributionRow }) {
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute left-1/2 top-full z-20 mt-1.5 w-64 -translate-x-1/2 rounded-lg border border-hairline bg-surface p-3 text-left text-[0.72rem] leading-relaxed text-ink-muted opacity-0 shadow-panel-hover transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
    >
      <p className="text-xs font-semibold text-ink">{routeLabel(row.route)}</p>
      <dl className="mt-1.5 space-y-1 tabular">
        <div className="flex justify-between gap-4">
          <dt>Contribution</dt>
          <dd
            className={clsx(
              "font-semibold",
              row.contributionPoints >= 0 ? "text-rise" : "text-fall",
            )}
          >
            {formatPoints(row.contributionPoints)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Route index</dt>
          <dd className="text-ink">
            {formatIndex(row.routeIndexPrevious)} → {formatIndex(row.routeIndexCurrent)}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>MoM</dt>
          <dd>{formatSignedPct(row.momPct)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>YoY</dt>
          <dd>{row.yoyPct == null ? "n/a" : formatSignedPct(row.yoyPct)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Traffic weight</dt>
          <dd>{formatFractionPct(row.trafficWeight, 2)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Weight in index</dt>
          <dd>{formatFractionPct(row.weightNormalized, 1)}</dd>
        </div>
      </dl>
    </div>
  );
}

function ContributionBarRow({
  row,
  maxAbs,
  selected,
  dimmed,
  onSelect,
}: {
  row: ContributionRow;
  maxAbs: number;
  selected: boolean;
  dimmed: boolean;
  onSelect: () => void;
}) {
  const positive = row.contributionPoints >= 0;
  const pct = barPercent(row.contributionPoints, maxAbs);

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${routeLabel(row.route)}, contribution ${formatPoints(
        row.contributionPoints,
      )}`}
      className={clsx(
        "group relative grid w-full grid-cols-[136px_1fr_78px] items-center gap-3 rounded-md px-2 py-2.5 text-left transition-colors sm:grid-cols-[172px_1fr_88px]",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
        selected ? "bg-brand-wash" : "hover:bg-surface-sunken",
        dimmed && !selected && "opacity-40",
      )}
    >
      {/* route + secondary metrics */}
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-ink">
          {routeLabel(row.route)}
        </div>
        <div className="mt-0.5 truncate text-[0.68rem] tabular text-ink-faint">
          {formatSignedPct(row.momPct)} MoM
          {row.trafficWeight != null && (
            <> · {formatFractionPct(row.trafficWeight, 1)} traffic</>
          )}
        </div>
      </div>

      {/* diverging track */}
      <div className="relative h-7">
        <div className="absolute inset-y-0.5 left-1/2 w-px bg-hairline-strong" />
        <div
          className={clsx(
            "absolute top-1/2 h-4 -translate-y-1/2",
            positive
              ? "left-1/2 rounded-r-sm bg-rise"
              : "right-1/2 rounded-l-sm bg-fall",
            selected && "ring-1 ring-inset ring-black/10",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* value */}
      <div
        className={clsx(
          "text-right text-sm font-semibold tabular",
          positive ? "text-rise" : "text-fall",
        )}
      >
        {positive ? "+" : "−"}
        {Math.abs(row.contributionPoints).toFixed(2)}
        <span className="ml-0.5 text-[0.6rem] font-normal text-ink-faint">pt</span>
      </div>

      <ContributionTooltip row={row} />
    </button>
  );
}

export function ContributionDivergingChart({
  rows,
  maxAbs,
  selectedRoute,
  onRouteSelect,
}: ContributionDivergingChartProps) {
  if (rows.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-ink-faint">
        No route contributions available for this period.
      </p>
    );
  }

  return (
    <div>
      {/* axis labels */}
      <div className="mb-1.5 grid grid-cols-[136px_1fr_78px] gap-3 px-2 sm:grid-cols-[172px_1fr_88px]">
        <span />
        <div className="flex items-center justify-between text-[0.62rem] font-semibold uppercase tracking-[0.1em]">
          <span className="text-fall">← Pulled index down</span>
          <span className="text-rise">Pushed index up →</span>
        </div>
        <span />
      </div>

      <div className="divide-y divide-hairline/70">
        {rows.map((row) => (
          <ContributionBarRow
            key={row.route}
            row={row}
            maxAbs={maxAbs}
            selected={selectedRoute === row.route}
            dimmed={selectedRoute != null}
            onSelect={() =>
              onRouteSelect(selectedRoute === row.route ? null : row.route)
            }
          />
        ))}
      </div>
    </div>
  );
}
