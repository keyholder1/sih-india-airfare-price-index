/**
 * Shapes the statistics engine's route-contribution output for display:
 * joins `price_index.route_contributions` with `route_inflation`, then
 * sorts / splits / ranks.
 *
 * This does NO statistics. Every number here comes straight from the engine
 * (`contribution_points`, `mom_inflation_pct`, `traffic_weight`, …). We only
 * reorder and group them.
 */
import type { AnalyticsResult, RouteStatus } from "../types";

export interface ContributionRow {
  route: string;
  origin: string;
  destination: string;
  /** engine: route_contributions[].contribution_points */
  contributionPoints: number;
  /** engine: route_contributions[].weight_normalized (share of index weight) */
  weightNormalized: number;
  routeIndexCurrent: number | null;
  routeIndexPrevious: number | null;
  /** engine: route_inflation[].mom_inflation_pct */
  momPct: number | null;
  /** engine: route_inflation[].yoy_inflation_pct (null in current data) */
  yoyPct: number | null;
  /** engine: route_inflation[].traffic_weight (route's share of national DGCA traffic) */
  trafficWeight: number | null;
  status: RouteStatus;
}

export interface ContributionBreakdown {
  /** all rows with a numeric contribution, sorted by |contribution| desc */
  ranked: ContributionRow[];
  positive: ContributionRow[];
  negative: ContributionRow[];
  /** largest absolute contribution — used to scale the diverging bars */
  maxAbs: number;
  droppedNoValue: number;
}

export function buildContributionBreakdown(
  analytics: AnalyticsResult,
): ContributionBreakdown {
  const inflByRoute = new Map(
    analytics.route_inflation.map((r) => [r.route, r]),
  );

  const all = analytics.price_index.route_contributions;
  const withValue = all.filter((c) => c.contribution_points != null);

  const rows: ContributionRow[] = withValue.map((c) => {
    const infl = inflByRoute.get(c.route);
    const [origin, destination] = c.route.split("-");
    return {
      route: c.route,
      origin,
      destination,
      contributionPoints: c.contribution_points as number,
      weightNormalized: c.weight_normalized,
      routeIndexCurrent: c.route_index_current,
      routeIndexPrevious: c.route_index_previous,
      momPct: infl?.mom_inflation_pct ?? null,
      yoyPct: infl?.yoy_inflation_pct ?? null,
      trafficWeight: infl?.traffic_weight ?? null,
      status: infl?.status ?? "OK",
    };
  });

  const ranked = [...rows].sort(
    (a, b) => Math.abs(b.contributionPoints) - Math.abs(a.contributionPoints),
  );
  const positive = rows
    .filter((r) => r.contributionPoints > 0)
    .sort((a, b) => b.contributionPoints - a.contributionPoints);
  const negative = rows
    .filter((r) => r.contributionPoints < 0)
    .sort((a, b) => a.contributionPoints - b.contributionPoints);

  const maxAbs = ranked.length
    ? Math.abs(ranked[0].contributionPoints)
    : 1;

  return {
    ranked,
    positive,
    negative,
    maxAbs,
    droppedNoValue: all.length - withValue.length,
  };
}
