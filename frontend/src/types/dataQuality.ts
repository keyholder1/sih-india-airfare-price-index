/**
 * Data-quality contract — from `data_quality.validate_fare_batch(...).to_dict()`
 * on the feature/news-event-context branch (src/data_quality/models.py).
 *
 * NOTE for later steps: this richer report lives on a feature branch that
 * is not yet merged. The always-available fallback is
 * `AnalyticsResult.price_index.cleaning_report` + the observations_* counts.
 */

export type SourceStatus = "HEALTHY" | "DEGRADED" | "FAILED" | "UNKNOWN";

export interface CompletenessReport {
  total_records: number;
  records_with_all_required_fields: number;
  records_missing_required_fields: number;
  records_missing_optional_fields: number;
  completeness_rate: number;
}

export interface SourceHealth {
  source: string;
  status: SourceStatus;
  observations_received: number;
  valid_observations: number;
  flagged_observations: number;
  rejected_observations: number;
  observation_validity_rate: number;
  routes_requested: number | null;
  routes_successful: number | null;
  routes_failed: number | null;
  route_success_rate: number | null;
  oldest_observation: string | null;
  newest_observation: string | null;
  data_age_seconds: number | null;
}

export interface RouteHealth {
  route: string;
  origin: string;
  destination: string;
  observations_total: number;
  observations_valid: number;
  observations_rejected: number;
  route_quality_rate: number;
  data_completeness: number;
  has_base_period_data: boolean | null;
  has_current_period_data: boolean | null;
}

export interface DataQualityResult {
  records_received: number;
  records_valid: number;
  records_flagged: number;
  records_rejected: number;
  completeness_rate: number;
  validity_rate: number;
  duplicate_rate: number;
  quality_score: number;
  quality_grade: string;
  rejection_reasons: Record<string, number>;
  flag_reasons: Record<string, number>;
  duplicate_count: number;
  exact_duplicate_count: number;
  potential_duplicate_count: number;
  completeness: CompletenessReport;
  source_health: SourceHealth[];
  route_health: RouteHealth[];
  overall_route_success_rate: number | null;
  overall_route_coverage: number | null;
}
