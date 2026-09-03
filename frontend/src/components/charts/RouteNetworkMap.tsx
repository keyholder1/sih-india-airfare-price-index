import { useMemo, useState } from "react";
import {
  INDIA_FRAME,
  INDIA_OUTLINE_PATH,
  INDIA_VIEWBOX,
} from "../../assets/india-outline";
import { chart } from "../../theme/tokens";
import type { RouteDetail } from "../../utils/routes";
import {
  divergingColor,
  heatMaxAbs,
  heatValue,
  HEAT_METRICS,
  type HeatMetric,
} from "../../utils/heat";
import {
  formatFractionPct,
  formatIndex,
  formatPoints,
  formatSignedPct,
  routeLabel,
} from "../../utils/format";

interface RouteNetworkMapProps {
  routes: RouteDetail[];
  metric: HeatMetric;
  selectedRoute: string | null;
  onRouteSelect: (route: string | null) => void;
}

function project(lon: number, lat: number) {
  const { lon0, lon1, lat0, lat1, w, h } = INDIA_FRAME;
  return {
    x: ((lon - lon0) / (lon1 - lon0)) * w,
    y: h - ((lat - lat0) / (lat1 - lat0)) * h,
  };
}

interface Arc {
  route: string;
  d: string;
  mid: { x: number; y: number };
  color: string;
  width: number;
  heat: number | null;
  detail: RouteDetail;
}

const { w: VW, h: VH } = INDIA_FRAME;

export function RouteNetworkMap({
  routes,
  metric,
  selectedRoute,
  onRouteSelect,
}: RouteNetworkMapProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  const metricMeta = HEAT_METRICS.find((m) => m.key === metric)!;
  const maxAbs = useMemo(() => heatMaxAbs(routes, metric), [routes, metric]);

  const { arcs, nodes } = useMemo(() => {
    const withCoords = routes.filter((r) => r.coords);
    const maxTraffic = Math.max(
      ...withCoords.map((r) => r.trafficWeight ?? 0),
      0.0001,
    );

    const arcs: Arc[] = withCoords.map((r) => {
      const c = r.coords!;
      const a = project(c.originLon, c.originLat);
      const b = project(c.destLon, c.destLat);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.hypot(dx, dy) || 1;
      const off = len * 0.14;
      const cx = (a.x + b.x) / 2 + (dy / len) * off;
      const cy = (a.y + b.y) / 2 + (-dx / len) * off;
      const heat = heatValue(r, metric);
      return {
        route: r.route,
        d: `M${a.x.toFixed(1)},${a.y.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(
          1,
        )} ${b.x.toFixed(1)},${b.y.toFixed(1)}`,
        mid: { x: (a.x + 2 * cx + b.x) / 4, y: (a.y + 2 * cy + b.y) / 4 },
        color: divergingColor(heat, maxAbs),
        width: 2.6 + ((r.trafficWeight ?? 0) / maxTraffic) * 3.6,
        heat,
        detail: r,
      };
    });

    const nodeMap = new Map<string, { iata: string; x: number; y: number }>();
    for (const r of withCoords) {
      const c = r.coords!;
      if (!nodeMap.has(r.origin)) {
        nodeMap.set(r.origin, { iata: r.origin, ...project(c.originLon, c.originLat) });
      }
      if (!nodeMap.has(r.destination)) {
        nodeMap.set(r.destination, {
          iata: r.destination,
          ...project(c.destLon, c.destLat),
        });
      }
    }
    return { arcs, nodes: [...nodeMap.values()] };
  }, [routes, metric, maxAbs]);

  const selectedDetail = routes.find((r) => r.route === selectedRoute);
  const selectedEndpoints = new Set(
    selectedDetail ? [selectedDetail.origin, selectedDetail.destination] : [],
  );

  const orderedArcs = [
    ...arcs.filter((a) => a.route !== selectedRoute && a.route !== hovered),
    ...arcs.filter((a) => a.route === hovered && a.route !== selectedRoute),
    ...arcs.filter((a) => a.route === selectedRoute),
  ];

  const activeArc = arcs.find((a) => a.route === (hovered ?? selectedRoute));

  return (
    <div>
      <div className="relative mx-auto max-w-[420px]">
        <svg
          viewBox={INDIA_VIEWBOX}
          className="h-auto w-full"
          role="img"
          aria-label={`Heatmap of domestic routes across India, coloured by ${metricMeta.label.toLowerCase()}`}
        >
          <path
            d={INDIA_OUTLINE_PATH}
            fill="#ECEDE9"
            stroke={chart.hairlineStrong}
            strokeWidth={1.5}
          />

          {orderedArcs.map((arc) => {
            const isSelected = arc.route === selectedRoute;
            const isHovered = arc.route === hovered;
            const dim = selectedRoute && !isSelected && !isHovered;
            return (
              <g key={arc.route}>
                <path
                  d={arc.d}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={20}
                  className="cursor-pointer"
                  onMouseEnter={() => setHovered(arc.route)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => onRouteSelect(isSelected ? null : arc.route)}
                />
                {/* soft light halo keeps every arc legible on the land fill */}
                <path
                  d={arc.d}
                  fill="none"
                  stroke="#FBFBF9"
                  strokeWidth={arc.width + (isSelected || isHovered ? 7 : 3)}
                  strokeLinecap="round"
                  opacity={dim ? 0.4 : 0.9}
                  className="pointer-events-none"
                />
                <path
                  d={arc.d}
                  fill="none"
                  stroke={arc.color}
                  strokeWidth={isSelected ? arc.width + 2.5 : arc.width}
                  strokeLinecap="round"
                  opacity={dim ? 0.35 : 1}
                  className="pointer-events-none transition-opacity"
                />
              </g>
            );
          })}

          {nodes.map((n) => {
            const active = selectedEndpoints.has(n.iata);
            return (
              <g key={n.iata} className="pointer-events-none">
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={active ? 9 : 5.5}
                  fill={active ? chart.brand : chart.surface}
                  stroke={active ? chart.brand : chart.inkMuted}
                  strokeWidth={2}
                />
                <text
                  x={n.x + 12}
                  y={n.y + 5}
                  fontSize={active ? 25 : 22}
                  fontWeight={active ? 700 : 600}
                  fill={active ? chart.ink : chart.inkMuted}
                  className="tabular"
                >
                  {n.iata}
                </text>
              </g>
            );
          })}
        </svg>

        {activeArc && (
          <RouteHeatTooltip arc={activeArc} metric={metric} />
        )}
      </div>

      <HeatLegend metric={metric} maxAbs={maxAbs} />
    </div>
  );
}

function RouteHeatTooltip({ arc, metric }: { arc: Arc; metric: HeatMetric }) {
  const r = arc.detail;
  const leftPct = (arc.mid.x / VW) * 100;
  const topPct = (arc.mid.y / VH) * 100;
  const anchor =
    leftPct < 32 ? "left-0" : leftPct > 68 ? "right-0 left-auto" : "-translate-x-1/2";

  const rows: { label: string; value: string; active: boolean }[] = [
    { label: "MoM", value: formatSignedPct(r.momPct), active: metric === "mom" },
    {
      label: "Contribution",
      value: formatPoints(r.contributionPoints),
      active: metric === "contribution",
    },
    { label: "Traffic weight", value: formatFractionPct(r.trafficWeight, 2), active: false },
    { label: "Route index", value: formatIndex(r.currentIndex), active: false },
    {
      label: "Volatility",
      value:
        formatFractionPct(r.volatility, 1) +
        (r.volatilityClass ? ` · ${r.volatilityClass.toLowerCase()}` : ""),
      active: false,
    },
  ];

  return (
    <div
      role="tooltip"
      className={`pointer-events-none absolute z-20 w-56 -translate-y-full rounded-lg border border-hairline bg-surface p-3 text-[0.72rem] shadow-panel-hover ${anchor}`}
      style={{ left: `${leftPct}%`, top: `calc(${topPct}% - 8px)` }}
    >
      <p className="text-xs font-semibold text-ink">
        {r.originCity && r.destinationCity
          ? `${r.originCity} → ${r.destinationCity}`
          : routeLabel(r.route)}
      </p>
      <p className="tabular text-[0.66rem] text-ink-faint">{routeLabel(r.route)}</p>
      <dl className="mt-1.5 space-y-1 tabular">
        {rows.map((row) => (
          <div
            key={row.label}
            className={`flex justify-between gap-4 ${
              row.active ? "font-semibold text-ink" : "text-ink-muted"
            }`}
          >
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function HeatLegend({ metric, maxAbs }: { metric: HeatMetric; maxAbs: number }) {
  const fmt = (v: number) =>
    metric === "mom" ? formatSignedPct(v, 1) : formatPoints(v, 2);
  const [downLabel, upLabel] =
    metric === "mom"
      ? ["fares fell", "fares rose"]
      : ["pulled index down", "pushed index up"];

  return (
    <div className="mt-4">
      <div className="mx-auto max-w-[320px]">
        <div
          className="h-2 w-full rounded-full"
          style={{
            background:
              "linear-gradient(to right, rgb(10,88,75), rgb(120,160,150), rgb(232,233,227), rgb(200,150,140), rgb(150,40,30))",
          }}
        />
        <div className="mt-1 flex justify-between text-[0.62rem] tabular text-ink-faint">
          <span>{fmt(-maxAbs)}</span>
          <span>0</span>
          <span>{fmt(maxAbs)}</span>
        </div>
        <div className="mt-0.5 flex justify-between text-[0.62rem] font-semibold uppercase tracking-[0.08em]">
          <span className="text-fall">{downLabel}</span>
          <span className="text-rise">{upLabel}</span>
        </div>
      </div>
      <p className="mt-2 text-center text-[0.66rem] text-ink-faint">
        colour ={" "}
        {metric === "mom"
          ? "route fare movement (MoM)"
          : "contribution to national index"}
        {"  ·  "}line weight = share of national traffic
      </p>
    </div>
  );
}
