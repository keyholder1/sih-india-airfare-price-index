import clsx from "clsx";
import { useMemo, useState } from "react";
import {
  sortRouteDetails,
  type RouteDetail,
  type RouteSortKey,
} from "../../utils/routes";
import {
  formatFractionPct,
  formatIndex,
  formatPoints,
  formatSignedPct,
  routeLabel,
} from "../../utils/format";
import { RouteStatusPill } from "./RouteStatusPill";

interface RouteTableProps {
  routes: RouteDetail[];
  selectedRoute: string | null;
  onRouteSelect: (route: string | null) => void;
}

interface Column {
  key: RouteSortKey;
  label: string;
  render: (r: RouteDetail) => React.ReactNode;
  align: "left" | "right";
  tone?: (r: RouteDetail) => string;
}

const COLUMNS: Column[] = [
  {
    key: "currentIndex",
    label: "Index",
    align: "right",
    render: (r) => formatIndex(r.currentIndex),
  },
  {
    key: "momPct",
    label: "MoM",
    align: "right",
    render: (r) => formatSignedPct(r.momPct),
    tone: (r) =>
      r.momPct == null ? "text-ink-faint" : r.momPct >= 0 ? "text-rise" : "text-fall",
  },
  {
    key: "trafficWeight",
    label: "Traffic wt.",
    align: "right",
    render: (r) => formatFractionPct(r.trafficWeight, 2),
  },
  {
    key: "contributionPoints",
    label: "Contribution",
    align: "right",
    render: (r) => formatPoints(r.contributionPoints),
    tone: (r) =>
      r.contributionPoints == null
        ? "text-ink-faint"
        : r.contributionPoints >= 0
          ? "text-rise"
          : "text-fall",
  },
  {
    key: "volatility",
    label: "Volatility",
    align: "right",
    render: (r) => formatFractionPct(r.volatility, 1),
  },
];

export function RouteTable({
  routes,
  selectedRoute,
  onRouteSelect,
}: RouteTableProps) {
  const [sortKey, setSortKey] = useState<RouteSortKey>("trafficWeight");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(
    () => sortRouteDetails(routes, sortKey, sortDir),
    [routes, sortKey, sortDir],
  );

  const toggleSort = (key: RouteSortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-hairline text-[0.68rem] uppercase tracking-[0.08em] text-ink-faint">
            <th className="py-2 pr-3 text-left font-semibold">Route</th>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className="py-2 pl-3 text-right font-semibold"
              >
                <button
                  type="button"
                  onClick={() => toggleSort(col.key)}
                  className={clsx(
                    "inline-flex items-center gap-1 transition-colors hover:text-ink",
                    sortKey === col.key && "text-ink",
                  )}
                >
                  {col.label}
                  <span className="text-[0.7em]">
                    {sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : "▾"}
                  </span>
                </button>
              </th>
            ))}
            <th className="py-2 pl-3 text-left font-semibold">Status</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const selected = r.route === selectedRoute;
            return (
              <tr
                key={r.route}
                onClick={() => onRouteSelect(selected ? null : r.route)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onRouteSelect(selected ? null : r.route);
                  }
                }}
                aria-selected={selected}
                className={clsx(
                  "cursor-pointer border-b border-hairline/70 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50",
                  selected ? "bg-brand-wash" : "hover:bg-surface-sunken",
                )}
              >
                <td className="py-2.5 pr-3">
                  <div className="font-semibold text-ink">
                    {r.originCity && r.destinationCity
                      ? `${r.originCity} → ${r.destinationCity}`
                      : routeLabel(r.route)}
                  </div>
                  <div className="text-[0.68rem] tabular text-ink-faint">
                    {routeLabel(r.route)}
                  </div>
                </td>
                {COLUMNS.map((col) => (
                  <td
                    key={col.key}
                    className={clsx(
                      "py-2.5 pl-3 text-right tabular",
                      col.tone ? col.tone(r) : "text-ink",
                    )}
                  >
                    {col.render(r)}
                  </td>
                ))}
                <td className="py-2.5 pl-3">
                  <RouteStatusPill status={r.status} size="sm" />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
