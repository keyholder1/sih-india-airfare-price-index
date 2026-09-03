/**
 * TypeScript mirror of the statistics engine's output contract.
 *
 * Source of truth: `AirfareAnalytics.calculate(...).to_dict()` and
 * `AirfarePriceIndex.calculate(...).to_dict()` in the `index-engine` branch
 * (src/index_engine/models.py, analytics.py, volatility.py, route_analysis.py).
 * These interfaces were derived from real generated output, not guessed.
 *
 * The frontend NEVER computes these values — it only reads them.
 */

export type RouteStatus =
  | "OK"
  | "NEW_ROUTE"
  | "DISCONTINUED"
  | "NO_BASE_DATA"
  | "INSUFFICIENT_DATA";

export type VolatilityClass = "LOW" | "MODERATE" | "HIGH" | "INSUFFICIENT_DATA";

/** Backend provenance classification (api/services/analytics_service.py's
 *  data_source field, sourced from data_access.classify_provenance).
 *  MIXED (some real + some mock observations) must never be treated as
 *  REAL. */
export type DataSource = "REAL" | "SYNTHETIC" | "MIXED" | "UNAVAILABLE";

/** One route's index for one period (price_index.route_indices[]). */
export interface RouteIndex {
  route: string;
  origin: string;
  destination: string;
  period: string;
  base_period_fare: number | null;
  period_fare: number | null;
  route_index: number | null;
  observations_used: number;
  weight_raw: number | null;
  weight_normalized: number | null;
  status: RouteStatus;
}

/** How much a route moved the national index MoM (price_index.route_contributions[]).
 *  Σ contribution_points === the national index's month-over-month point change. */
export interface RouteContribution {
  route: string;
  weight_normalized: number;
  route_index_current: number | null;
  route_index_previous: number | null;
  contribution_points: number | null;
}

export interface CleaningReport {
  total_input: number;
  total_valid: number;
  total_removed: number;
  removed_by_reason: Record<string, number>;
}

export interface PriceIndex {
  base_period: string;
  current_period: string;
  national_index: number | null;
  mom_change_pct: number | null;
  /** null whenever <12 months of history exists (currently always null in demo data). */
  yoy_change_pct: number | null;
  routes_covered: number;
  routes_total: number;
  observations_used: number;
  coverage_rate: number;
  observations_received: number;
  observations_rejected: number;
  outliers_flagged: number;
  routes_expected: number;
  routes_with_data: number;
  representative_method: string;
  aggregation_method: string;
  route_indices: RouteIndex[];
  route_contributions: RouteContribution[];
  quality_flags: string[];
  cleaning_report: CleaningReport;
}

export interface RouteVolatility {
  route: string;
  period: string;
  volatility: number | null;
  classification: VolatilityClass;
  observations_used: number;
  method: string;
}

export interface BookingHorizonVolatility {
  /** Engine buckets: "0-3" | "4-7" | "8-14" | "15-30" | "31-60" | "61+" (days before departure). */
  bucket: string;
  volatility: number | null;
  classification: VolatilityClass;
  observations_used: number;
}

export interface VolatilityResult {
  period: string;
  method: string;
  national_volatility: number | null;
  national_classification: VolatilityClass;
  route_volatility: RouteVolatility[];
  high_volatility_routes: string[];
  low_volatility_routes: string[];
  observations_used: number;
  booking_horizon_volatility: BookingHorizonVolatility[];
}

/** route_inflation[] — inflation, importance and stability for one route, together. */
export interface RouteInflationRow {
  route: string;
  origin: string;
  destination: string;
  current_index: number | null;
  mom_inflation_pct: number | null;
  yoy_inflation_pct: number | null;
  /** share of covered-route weight */
  weight: number | null;
  /** route's share of national DGCA passenger traffic */
  traffic_weight: number | null;
  contribution: number | null;
  volatility: number | null;
  status: RouteStatus;
}

export type RankingKey =
  | "highest_mom_inflation"
  | "lowest_mom_inflation"
  | "highest_yoy_inflation"
  | "lowest_yoy_inflation"
  | "largest_positive_contributors"
  | "largest_negative_contributors"
  | "highest_traffic_weight"
  | "highest_volatility";

export interface RouteMapObject {
  origin: string;
  destination: string;
  origin_lat: number;
  origin_lon: number;
  destination_lat: number;
  destination_lon: number;
  inflation_mom: number | null;
  inflation_yoy: number | null;
  volatility: number | null;
  traffic_weight: number | null;
  contribution: number | null;
  status: RouteStatus;
}

/**
 * Origin x Destination inflation matrix (`AirfareAnalytics.calculate(...)
 * .inflation_matrix(metric=...)`, JSON-encoded by
 * api/services/analytics_service.py). `values[i][j]` corresponds to
 * `origins[i]` -> `destinations[j]`; `null` means no data for that pair,
 * never zero -- a route with no data is not a route with zero inflation.
 */
export interface InflationMatrix {
  origins: string[];
  destinations: string[];
  values: (number | null)[][];
}

export interface AnalyticsResult {
  price_index: PriceIndex;
  volatility: VolatilityResult;
  route_inflation: RouteInflationRow[];
  rankings: Record<RankingKey, RouteInflationRow[]>;
  route_map_objects: RouteMapObject[];
  traffic_weight_coverage: number | null;
  affordability: unknown | null;
  /** Provenance of the observations behind this payload -- REAL only
   *  when every observation is genuinely scraped, MIXED when some are
   *  mock, SYNTHETIC when all are mock/demo, UNAVAILABLE when there was
   *  nothing to compute from at all. Authoritative -- never infer
   *  provenance from DATA_MODE or from whether a value happens to be
   *  non-null (see data_access.classify_provenance). */
  data_source: DataSource;
  /** Not present in mock-mode fixtures (older contract) -- optional. */
  inflation_matrix_mom?: InflationMatrix;
  inflation_matrix_yoy?: InflationMatrix;
}

/** One point of `POST /index/timeseries` output (index_timeseries.json). */
export interface IndexTimeseriesPoint {
  period: string;
  national_index: number | null;
  mom_change_pct: number | null;
  yoy_change_pct: number | null;
}
