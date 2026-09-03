/**
 * National baseline forecast + MoSPI CPI benchmark — from
 * `GET /api/v1/analytics/forecast` (api/services/analytics_service.py),
 * mirroring forecasting.results.ForecastResult /
 * forecasting.cpi_results.CPIBenchmarkResult's own to_dict() shapes.
 */
import type { DataSource } from "./analytics";

export interface NationalForecast {
  forecast_period: string;
  forecast_value: number | null;
  model_used: string;
  horizon: number;
  training_period: string[];
  data_points_used: number;
  lower_bound: number | null;
  upper_bound: number | null;
  status: string;
  is_synthetic_data: boolean;
  notes: string | null;
}

export interface CPIPeriodComparison {
  period: string;
  our_index_rebased: number | null;
  mospi_index_rebased: number | null;
  our_mom_pct: number | null;
  mospi_mom_pct: number | null;
  mom_difference_pct_points: number | null;
  our_yoy_pct: number | null;
  mospi_yoy_pct: number | null;
  yoy_difference_pct_points: number | null;
  mospi_imputed: boolean;
  included_in_metrics: boolean;
  exclusion_reason: string | null;
}

export interface CPIBenchmark {
  overlap_start: string | null;
  overlap_end: string | null;
  overlap_period_count: number;
  rebase_period: string | null;
  comparisons: CPIPeriodComparison[];
  mean_absolute_mom_difference_pct_points: number | null;
  mom_correlation: number | null;
  mom_correlation_status: string;
  yoy_comparison_status: string;
  mean_absolute_yoy_difference_pct_points: number | null;
  yoy_period_count: number;
  mospi_base_year: number | null;
  mospi_source_file: string | null;
  status: string;
  is_synthetic_airfare_data: boolean;
  notes: string | null;
}

export interface ForecastPayload {
  national_forecast: NationalForecast;
  cpi_benchmark: CPIBenchmark | null;
  data_source: DataSource;
}
