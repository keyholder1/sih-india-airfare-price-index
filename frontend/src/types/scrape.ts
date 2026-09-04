/**
 * On-demand two-route scrape job -- POST /api/v1/scrape/jobs,
 * GET /api/v1/scrape/jobs/{id} (api/routes/scrape.py). A real, live
 * SerpApi call triggered by the viewer, not a simulation -- see
 * api/services/scrape_job_service.py.
 */

export type ScrapeJobStatus =
  | "queued"
  | "scraping"
  | "validating"
  | "indexing"
  | "done"
  | "failed";

/** One real, individual fare row from fare_observations for the looked-up
 *  route -- not a derived/rounded summary. */
export interface RouteFareRow {
  airline: string | null;
  flight_date: string | null;
  booking_date: string | null;
  total_fare: number;
  currency: string | null;
  source: string | null;
}

export interface ScrapeJobResult {
  route: string;
  collected_at: string;
  /** True when this route already had previously-recorded real
   *  observations and the pipeline reused them instead of spending a
   *  fresh SerpApi call -- see api/services/scrape_job_service.py. */
  from_cache: boolean;
  /** Map-display metadata only -- never part of any index/weight
   *  calculation. Null for an airport with no verified city/coordinate
   *  mapping (index_engine.city_mapping / geo_metadata), same as any
   *  other route on the map. This route is never added to the tracked/
   *  weighted route set the map and table otherwise draw from, so these
   *  fields are what let the frontend show it anyway. */
  origin_city: string | null;
  destination_city: string | null;
  origin_lat: number | null;
  origin_lon: number | null;
  destination_lat: number | null;
  destination_lon: number | null;
  /** Only present on a fresh (from_cache=false) call -- describes that
   *  specific SerpApi call, not the route's cumulative history. */
  raw_observations_collected: number | null;
  validated_observations: number | null;
  rejected_observations: number | null;
  rejection_reasons: Record<string, number> | null;
  quality_score: number | null;
  quality_grade: string | null;
  route_status: string;
  route_index: number | null;
  route_observations_used: number;
  /** Actual rupee fares behind route_index -- base-period vs current-period
   *  average fare for this route (index_engine.RouteIndexResult), and the
   *  real individual fares (fare_min/max/mean/median + a cheapest-first
   *  sample) collected for it across every run, cache hit or not. */
  route_base_period_fare: number | null;
  route_period_fare: number | null;
  fare_currency: string | null;
  fare_count: number;
  fare_min: number | null;
  fare_max: number | null;
  fare_mean: number | null;
  fare_median: number | null;
  sample_fares: RouteFareRow[];
  updated_national_index: number | null;
  updated_national_index_data_source: string;
  updated_base_period: string;
  updated_current_period: string;
  updated_routes_covered: number;
  updated_routes_total: number;
}

export interface ScrapeJob {
  id: string;
  origin: string;
  destination: string;
  status: ScrapeJobStatus;
  message: string | null;
  result: ScrapeJobResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}
