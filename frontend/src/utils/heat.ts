/**
 * Heatmap colour + metric helpers for the route map.
 *
 * Pure presentation: `heatValue` just reads an existing engine field off a
 * RouteDetail, `heatMaxAbs` is display-scale normalisation (like an axis
 * auto-range), and `divergingColor` is a colour interpolation. No statistic
 * is computed or invented here.
 *
 * Colour language matches the rest of the dashboard:
 *   positive movement (fares up)   → rise  (clay)
 *   negative movement (fares down) → fall  (teal)
 *   little / no movement           → near-neutral
 */
import type { RouteDetail } from "./routes";

export type HeatMetric = "mom" | "contribution";

export const HEAT_METRICS: {
  key: HeatMetric;
  label: string;
  short: string;
  hint: string;
}[] = [
  {
    key: "mom",
    label: "Fare movement",
    short: "MoM",
    hint: "Month-over-month change in each route's fare index",
  },
  {
    key: "contribution",
    label: "Contribution to index",
    short: "Contribution",
    hint: "Each route's contribution (points) to the national index's monthly move",
  },
];

export function heatValue(r: RouteDetail, metric: HeatMetric): number | null {
  return metric === "mom" ? r.momPct : r.contributionPoints;
}

export function heatMaxAbs(rows: RouteDetail[], metric: HeatMetric): number {
  const magnitudes = rows
    .map((r) => heatValue(r, metric))
    .filter((v): v is number => v != null)
    .map((v) => Math.abs(v));
  return magnitudes.length ? Math.max(...magnitudes) : 1;
}

type RGB = [number, number, number];

// Endpoints are a touch deeper than the UI tokens so the strongest routes
// really read on a projector; the neutral is the map's land fill.
const NEUTRAL: RGB = [232, 233, 227];
const RISE_DEEP: RGB = [150, 40, 30];
const FALL_DEEP: RGB = [10, 88, 75];

const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
const mix = (a: RGB, b: RGB, t: number) =>
  `rgb(${lerp(a[0], b[0], t)}, ${lerp(a[1], b[1], t)}, ${lerp(a[2], b[2], t)})`;

/**
 * Colour for `value` on a diverging scale spanning [-maxAbs, +maxAbs].
 * A mild gamma keeps small-but-real movements visible rather than washed out.
 */
export function divergingColor(
  value: number | null,
  maxAbs: number,
  { minIntensity = 0.34 }: { minIntensity?: number } = {},
): string {
  if (value == null || maxAbs <= 0) return "rgb(176, 178, 170)";
  const t = Math.max(-1, Math.min(1, value / maxAbs));
  // gentle gamma lifts mid-range routes so the map isn't just one hot line
  const eased = Math.max(minIntensity, Math.pow(Math.abs(t), 0.5));
  return t >= 0 ? mix(NEUTRAL, RISE_DEEP, eased) : mix(NEUTRAL, FALL_DEEP, eased);
}
