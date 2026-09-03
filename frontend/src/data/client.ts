/**
 * Data-access layer. Components import ONLY from here — never from the
 * fixture files or `fetch` directly. Swapping to the real API is contained
 * entirely within this file.
 */
import {
  API_BASE_URL,
  API_KEY,
  DATA_MODE,
  MOCK_LATENCY_MS,
} from "./dataSource";
import type {
  AnalyticsResult,
  DataQualityResult,
  DataStatus,
  ForecastPayload,
  IndexTimeseriesPoint,
  RecommendedRoutesFile,
  RouteContext,
} from "../types";

import analyticsFixture from "./fixtures/analytics.json";
import timeseriesFixture from "./fixtures/index_timeseries.json";
import routesFixture from "./fixtures/recommended_routes.json";
import dataQualityFixture from "./fixtures/data_quality.json";

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

async function apiGet<T>(path: string): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  const res = await fetch(`${API_BASE_URL}${path}`, { headers });
  if (!res.ok) {
    throw new Error(`API ${path} responded ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

// --- endpoints ---------------------------------------------------------------
// Backend: api/routes/analytics.py, mounted at /api/v1/analytics* (see
// api/main.py). Every response here is the engine's own dataclass
// .to_dict() shape -- the same contract these types were written against
// (see each type file's header comment in ../types/).

export function getAnalytics(): Promise<AnalyticsResult> {
  if (DATA_MODE === "api") return apiGet<AnalyticsResult>("/api/v1/analytics");
  return delay(analyticsFixture as unknown as AnalyticsResult);
}

/**
 * Covers the whole demo year so real scraper output lands wherever it
 * exists on the backend (see src/engine/data_access.py) regardless of
 * which months that happens to be; months without data come back with
 * null values (see IndexTimeseriesPoint), never fabricated.
 */
const TIMESERIES_START = "2026-01";
const TIMESERIES_END = "2026-12";

export function getTimeseries(): Promise<IndexTimeseriesPoint[]> {
  if (DATA_MODE === "api") {
    return apiGet<IndexTimeseriesPoint[]>(
      `/api/v1/analytics/timeseries?start_date=${TIMESERIES_START}&end_date=${TIMESERIES_END}`
    );
  }
  return delay(timeseriesFixture as unknown as IndexTimeseriesPoint[]);
}

export function getRecommendedRoutes(): Promise<RecommendedRoutesFile> {
  if (DATA_MODE === "api") return apiGet<RecommendedRoutesFile>("/api/v1/analytics/routes/recommended");
  return delay(routesFixture as unknown as RecommendedRoutesFile);
}

export function getDataQuality(): Promise<DataQualityResult> {
  if (DATA_MODE === "api") return apiGet<DataQualityResult>("/api/v1/analytics/data-quality");
  return delay(dataQualityFixture as unknown as DataQualityResult);
}

/** No mock fixture exists for this (added after the fixture set was
 * frozen) -- mock mode returns a small, clearly-labelled placeholder
 * instead of a network call. */
function mockRouteContext(route: string): RouteContext {
  return {
    route,
    significant_movement: false,
    movement_direction: null,
    movement_pct: null,
    events: [],
    data_source: "synthetic",
  };
}

export function getRouteContext(route: string): Promise<RouteContext> {
  if (DATA_MODE === "api") return apiGet<RouteContext>(`/api/v1/routes/${route}/context`);
  return delay(mockRouteContext(route));
}

function mockForecast(): ForecastPayload {
  return {
    national_forecast: {
      forecast_period: "2026-09",
      forecast_value: null,
      model_used: "naive",
      horizon: 1,
      training_period: [],
      data_points_used: 0,
      lower_bound: null,
      upper_bound: null,
      status: "INSUFFICIENT_DATA",
      is_synthetic_data: true,
      notes: "Mock mode has no forecasting fixture.",
    },
    cpi_benchmark: null,
  };
}

export function getForecast(): Promise<ForecastPayload> {
  if (DATA_MODE === "api") return apiGet<ForecastPayload>("/api/v1/analytics/forecast");
  return delay(mockForecast());
}

/**
 * Provenance of the current figures. Derived client-side from whether the
 * backend actually had real (non-mock) scraped observations to compute
 * from -- see src/engine/real_adapters.py / data_access.py's is_mock
 * handling, which is the same signal api/v1/dashboard/summary's
 * data_source field reflects.
 */
export async function getDataStatus(): Promise<DataStatus> {
  const analytics = await getAnalytics();
  const hasRealData = analytics.price_index.national_index !== null && DATA_MODE === "api";
  if (hasRealData) {
    return {
      level: "LIVE",
      label: "Live scraped data",
      detail: "Airfare observations behind these figures were collected by the scraper, not fabricated.",
      asOf: analytics.price_index.current_period,
    };
  }
  return {
    level: "SYNTHETIC",
    label: "Demonstration / synthetic data",
    detail:
      "Airfare observations behind these figures are synthetic. The statistical " +
      "pipeline, DGCA passenger-traffic weights and route metadata are real; the " +
      "fare values are not, and these numbers are not a measurement of Indian airfare inflation.",
    asOf: analytics.price_index.current_period,
  };
}
