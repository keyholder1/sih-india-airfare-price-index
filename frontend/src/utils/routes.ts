/**
 * Assembles one flat per-route record from the engine's several output
 * arrays (`route_inflation`, `route_indices`, `route_contributions`,
 * `volatility.route_volatility`, `route_map_objects`). City names come
 * live from `route_inflation`'s own `origin_city`/`destination_city`
 * (any known airport), falling back to the separate, static
 * `recommended_routes.json` candidate list only when the live field has
 * no mapping. Tier/priority still come from `recommended_routes.json`
 * only -- those are inherently about the curated candidate list, not a
 * live property of a route.
 *
 * Pure joining + light label formatting. Every metric is an engine value;
 * nothing is (re)computed here.
 */
import type {
  AnalyticsResult,
  RecommendedRoutesFile,
  RouteStatus,
  ScrapeJobResult,
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

  /** True only for a route drawn from buildAdHocRouteDetail -- one just
   *  run through Section 8's on-demand pipeline, not part of the tracked/
   *  DGCA-weighted set. Undefined (never explicitly false) for every
   *  route buildRouteDetails produces. */
  isAdHoc?: boolean;
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
      // Prefer the engine's own live IATA_TO_CITY lookup (covers any known
      // airport, not just routes in the static recommended_routes.json
      // candidate list) -- fall back to the recommended file only for a
      // route the live field has no verified mapping for.
      originCity: infl.origin_city ?? (rec ? titleCase(rec.origin_city) : null),
      destinationCity: infl.destination_city ?? (rec ? titleCase(rec.destination_city) : null),

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

/**
 * A route run through Section 8's on-demand pipeline is deliberately never
 * added to the tracked/DGCA-weighted route set (see api/services/
 * scrape_job_service.py's `_route_spec`), so it never appears in
 * `analytics.route_inflation` and therefore never in `buildRouteDetails`'
 * output -- the map, table and detail panel all draw from that array.
 * Without this, running the pipeline for a route outside the existing 20
 * makes it vanish everywhere except the small results panel under the
 * form itself, even though it's real data now sitting in Postgres.
 *
 * Builds one supplementary RouteDetail from the job result so it can be
 * drawn alongside the tracked routes -- clearly not part of national-index
 * weighting (trafficWeight/contributionPoints stay null, same as any
 * route the engine has no weight for). Returns null when the route is
 * already tracked (buildRouteDetails already covers it, don't duplicate
 * the arc) or when either airport has no verified coordinate mapping
 * (index_engine.geo_metadata) -- never guessed/placed at a fallback point.
 */
export function buildAdHocRouteDetail(
  result: ScrapeJobResult,
  existing: RouteDetail[],
): RouteDetail | null {
  if (existing.some((r) => r.route === result.route)) return null;
  if (
    result.origin_lat == null ||
    result.origin_lon == null ||
    result.destination_lat == null ||
    result.destination_lon == null
  ) {
    return null;
  }
  const [origin, destination] = result.route.split("-");

  return {
    route: result.route,
    origin,
    destination,
    originCity: result.origin_city,
    destinationCity: result.destination_city,

    currentIndex: result.route_index,
    previousIndex: null,
    momPct: null,
    yoyPct: null,

    trafficWeight: null,
    weightInIndex: null,
    contributionPoints: null,

    volatility: null,
    volatilityClass: null,

    status: result.route_status as RouteStatus,
    observationsUsed: result.route_observations_used,

    basePeriodFare: result.route_base_period_fare,
    periodFare: result.route_period_fare,

    coords: {
      originLat: result.origin_lat,
      originLon: result.origin_lon,
      destLat: result.destination_lat,
      destLon: result.destination_lon,
    },

    priority: null,
    tier: null,
    isAdHoc: true,
  };
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
