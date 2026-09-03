/** Formatting helpers. Presentation only — no statistics happen here. */

const MINUS = "−"; // real minus sign, not a hyphen
const ARROW_UP = "↑";
const ARROW_DOWN = "↓";

export function formatIndex(value: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

/** e.g. 2.81 → "+2.81%" ; -0.87 → "−0.87%" ; null → "n/a" */
export function formatSignedPct(value: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "n/a";
  const sign = value >= 0 ? "+" : MINUS;
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function formatPct(value: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** 0.088 → "8.8%" (fraction to percent) */
export function formatFractionPct(value: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatInt(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-IN");
}

export function formatINR(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

export function formatPoints(value: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "n/a";
  const sign = value >= 0 ? "+" : MINUS;
  return `${sign}${Math.abs(value).toFixed(digits)} pt`;
}

export function directionArrow(value: number | null): string {
  if (value == null || value === 0) return "";
  return value > 0 ? ARROW_UP : ARROW_DOWN;
}

/** "BOM-DEL" → "BOM → DEL" */
export function routeLabel(route: string): string {
  const [o, d] = route.split("-");
  return d ? `${o} → ${d}` : route;
}

/** "2026-08" → "Aug 2026" */
export function formatPeriod(period: string): string {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  const month = new Date(y, m - 1, 1).toLocaleString("en-US", { month: "short" });
  return `${month} ${y}`;
}

/** Shift a "YYYY-MM" period by N months. Label arithmetic only — the
 *  engine owns every actual month-to-month calculation. */
export function shiftPeriod(period: string, months: number): string {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  const d = new Date(y, m - 1 + months, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Engine booking-horizon buckets → judge-friendly labels. */
export function horizonLabel(bucket: string): string {
  const map: Record<string, string> = {
    "0-3": "≤ 3 days",
    "4-7": "4–7 days",
    "8-14": "8–14 days",
    "15-30": "15–30 days",
    "31-60": "31–60 days",
    "61+": "60+ days",
  };
  return map[bucket] ?? bucket;
}
