import clsx from "clsx";
import type { RouteDetail } from "../../utils/routes";
import {
  formatFractionPct,
  formatINR,
  formatIndex,
  formatPoints,
  formatSignedPct,
  routeLabel,
} from "../../utils/format";
import { RouteStatusPill } from "./RouteStatusPill";

interface RouteDetailPanelProps {
  route: RouteDetail | null;
  onClear: () => void;
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: string;
}) {
  return (
    <div>
      <dt className="text-[0.66rem] uppercase tracking-wide text-ink-faint">
        {label}
      </dt>
      <dd className={clsx("mt-0.5 text-base font-semibold tabular", tone ?? "text-ink")}>
        {value}
      </dd>
      {sub && <div className="text-[0.68rem] tabular text-ink-faint">{sub}</div>}
    </div>
  );
}

export function RouteDetailPanel({ route, onClear }: RouteDetailPanelProps) {
  if (!route) {
    return (
      <div className="flex h-full min-h-[220px] flex-col items-center justify-center rounded-panel border border-dashed border-hairline-strong bg-surface-sunken p-6 text-center">
        <p className="text-sm font-medium text-ink-muted">No route selected</p>
        <p className="mt-1 max-w-xs text-xs text-ink-faint">
          Pick a route from the map, the table, or the “Why did the index move?”
          chart above to see how it behaves.
        </p>
      </div>
    );
  }

  const momTone =
    route.momPct == null
      ? "text-ink-faint"
      : route.momPct >= 0
        ? "text-rise"
        : "text-fall";
  const contribTone =
    route.contributionPoints == null
      ? "text-ink-faint"
      : route.contributionPoints >= 0
        ? "text-rise"
        : "text-fall";

  // "index vs base" bar: how far the route's current index sits from 100.
  const idx = route.currentIndex ?? 100;
  const spread = 40; // ± index points shown across the track
  const pct = Math.max(-1, Math.min(1, (idx - 100) / spread));

  return (
    <div className="rounded-panel border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold tracking-tight text-ink">
              {route.originCity && route.destinationCity
                ? `${route.originCity} → ${route.destinationCity}`
                : routeLabel(route.route)}
            </h3>
            <RouteStatusPill status={route.status} size="sm" />
          </div>
          <p className="mt-0.5 text-xs tabular text-ink-faint">
            {routeLabel(route.route)}
            {route.tier != null && route.priority != null && (
              <>
                {" "}
                · Tier {route.tier} · #{route.priority} by national traffic
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-md px-2 py-1 text-xs font-medium text-ink-faint transition-colors hover:bg-surface-sunken hover:text-ink"
        >
          Clear
        </button>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
        <Metric
          label="Route index"
          value={formatIndex(route.currentIndex)}
          sub={
            route.previousIndex != null
              ? `from ${formatIndex(route.previousIndex)} last month`
              : undefined
          }
        />
        <Metric label="MoM" value={formatSignedPct(route.momPct)} tone={momTone} />
        <Metric
          label="YoY"
          value={route.yoyPct == null ? "N/A" : formatSignedPct(route.yoyPct)}
          sub={route.yoyPct == null ? "needs 12 mo history" : undefined}
        />
        <Metric
          label="Traffic weight"
          value={formatFractionPct(route.trafficWeight, 2)}
          sub="share of national pax"
        />
        <Metric
          label="Contribution"
          value={formatPoints(route.contributionPoints)}
          tone={contribTone}
          sub="to national index MoM"
        />
        <Metric
          label="Volatility"
          value={formatFractionPct(route.volatility, 1)}
          sub={route.volatilityClass ? route.volatilityClass.toLowerCase() : undefined}
        />
      </dl>

      {/* index vs base period */}
      <div className="mt-5 border-t border-hairline pt-4">
        <div className="flex items-baseline justify-between text-[0.66rem] uppercase tracking-wide text-ink-faint">
          <span>Fare vs base period (Jan = 100)</span>
          <span className="tabular text-ink-muted">
            {formatINR(route.basePeriodFare)} → {formatINR(route.periodFare)}
          </span>
        </div>
        <div className="relative mt-2 h-6">
          <div className="absolute inset-y-1.5 left-1/2 w-px bg-hairline-strong" />
          <div
            className={clsx(
              "absolute top-1/2 h-3 -translate-y-1/2 rounded-sm",
              pct >= 0 ? "left-1/2 bg-rise" : "right-1/2 bg-fall",
            )}
            style={{ width: `${Math.abs(pct) * 50}%` }}
          />
          <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 text-[0.6rem] tabular text-ink-faint">
            100
          </div>
        </div>
        <p className="mt-6 text-[0.68rem] tabular text-ink-faint">
          {route.observationsUsed != null
            ? `${route.observationsUsed} observations this month`
            : "observation count unavailable"}
        </p>
      </div>
    </div>
  );
}
