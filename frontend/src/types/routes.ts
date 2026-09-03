/**
 * Route metadata — from data/routes/recommended_routes.json in the repo
 * (produced by src/index_engine/route_selection.py from real DGCA traffic).
 * REAL / PUBLIC data.
 */

export interface RecommendedRoute {
  origin_city: string;
  destination_city: string;
  origin_iata: string;
  destination_iata: string;
  priority: number;
  tier: 1 | 2 | 3;
  /** route's share of national domestic passenger traffic (DGCA-derived) */
  national_weight: number;
  currently_covered: boolean;
}

export interface RecommendedRoutesFile {
  source: string;
  weight_period: string;
  tier_cutoffs: {
    tier_1_end_rank: number;
    tier_2_end_rank: number;
    tier_3_end_rank: number;
  };
  routes: RecommendedRoute[];
}
