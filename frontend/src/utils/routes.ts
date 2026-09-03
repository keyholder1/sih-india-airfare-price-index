/**
 * Assembles one flat per-route record from the engine's several output
 * arrays (`route_inflation`, `route_indices`, `route_contributions`,
 * `volatility.route_volatility`, `route_map_objects`) plus optional city
 * names from `recommended_routes.json`.
 *
 * Pure joining + light label formatting. Every metric is an engine value;
 * nothing is (re)computed here.
 */
import type {
  AnalyticsResult,
  RecommendedRoutesFile,
  RouteStatus,
  VolatilityClass,
} from "../types";

export interface RouteCoords {
  originLat: number;
  originLon: number;
  destLat: number;
  destLon: number;
}

export interface RouteDetail {
  route: string;
  origin: string;
  destination: string;
  originCity: string | null;
  destinationCity: string | null;

  currentIndex: number | null;
  previousIndex: number | null;
  momPct: number | null;
  yoyPct: number | null;

  /** route's share of national domestic passenger traffic (DGCA-derived) */
  trafficWeight: number | null;
  /** route's share of the index basket weight */
  weightInIndex: number | null;
  contributionPoints: number | null;

  volatility: number | null;
  volatilityClass: VolatilityClass | null;

  status: RouteStatus;
  observationsUsed: number | null;

  basePeriodFare: number | null;
  periodFare: number | null;

  coords: RouteCoords | null;

  priority: number | null;
  tier: 1 | 2 | 3 | null;
}

function titleCase(name: string): string {
  return name
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bAnd\b/g, "and");
}

export function buildRouteDetails(
  analytics: AnalyticsResult,
  recommended: RecommendedRoutesFile | null,
): RouteDetail[] {
  const indexByRoute = new Map(
    analytics.price_index.route_indices.map((r) => [r.route, r]),
  );
  const contribByRoute = new Map(
    analytics.price_index.route_contributions.map((r) => [r.route, r]),
  );
  const volByRoute = new Map(
    analytics.volatility.route_volatility.map((r) => [r.route, r]),
  );
  const mapByRoute = new Map(
    analytics.route_map_objects.map((r) => [`${r.origin}-${r.destination}`, r]),
  );
  const recByRoute = new Map(
    (recommended?.routes ?? []).map((r) => [
      `${r.origin_iata}-${r.destination_iata}`,
      r,
    ]),
  );

  return analytics.route_inflation.map((infl) => {
    const idx = indexByRoute.get(infl.route);
    const contrib = contribByRoute.get(infl.route);
    const vol = volByRoute.get(infl.route);
    const geo = mapByRoute.get(infl.route);
    const rec = recByRoute.get(infl.route);

    return {
      route: infl.route,
      origin: infl.origin,
      destination: infl.destination,
      originCity: rec ? titleCase(rec.origin_city) : null,
      destinationCity: rec ? titleCase(rec.destination_city) : null,

      currentIndex: infl.current_index,
      previousIndex: contrib?.route_index_previous ?? null,
      momPct: infl.mom_inflation_pct,
      yoyPct: infl.yoy_inflation_pct,

      trafficWeight: infl.traffic_weight,
      weightInIndex: infl.weight ?? idx?.weight_normalized ?? null,
      contributionPoints: infl.contribution,

      volatility: infl.volatility ?? vol?.volatility ?? null,
      volatilityClass: vol?.classification ?? null,

      status: infl.status,
      observationsUsed: idx?.observations_used ?? null,

      basePeriodFare: idx?.base_period_fare ?? null,
      periodFare: idx?.period_fare ?? null,

      coords: geo
        ? {
            originLat: geo.origin_lat,
            originLon: geo.origin_lon,
            destLat: geo.destination_lat,
            destLon: geo.destination_lon,
          }
        : null,

      priority: rec?.priority ?? null,
      tier: rec?.tier ?? null,
    };
  });
}

export type RouteSortKey =
  | "trafficWeight"
  | "currentIndex"
  | "momPct"
  | "contributionPoints"
  | "volatility";

export function sortRouteDetails(
  rows: RouteDetail[],
  key: RouteSortKey,
  dir: "asc" | "desc",
): RouteDetail[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1; // nulls always last
    if (bv == null) return -1;
    return (av - bv) * sign;
  });
}

export function findRouteDetail(
  rows: RouteDetail[],
  route: string | null,
): RouteDetail | null {
  if (!route) return null;
  return rows.find((r) => r.route === route) ?? null;
}
