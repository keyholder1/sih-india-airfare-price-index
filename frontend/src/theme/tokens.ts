/**
 * Chart-facing colour tokens. Recharts needs plain JS values, so the
 * palette lives here as well as in tailwind.config.ts. Keep the two in
 * sync — same hex, same meaning.
 */
export const chart = {
  ink: "#14161C",
  inkMuted: "#565B66",
  inkFaint: "#8B909B",
  hairline: "#E7E6DF",
  hairlineStrong: "#D9D8CF",
  surface: "#FFFFFF",

  brand: "#1B2E4E",
  brandSoft: "#24406E",
  accent: "#2563EB",

  /** airfares rose (index up) */
  rise: "#B23A2E",
  /** airfares fell (index down) */
  fall: "#0E7C6B",

  /** baseline / reference marks (index = 100) */
  baseline: "#9AA0AC",

  synth: "#9A5B08",
} as const;

/** Base period is pinned to 100 by the statistics engine. */
export const INDEX_BASELINE = 100;
