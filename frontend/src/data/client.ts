/**
 * Data-access layer. Components import ONLY from here — never from the
 * fixture files or `fetch` directly. Swapping to the real API is contained
 * entirely within this file.
 */
import {
  API_BASE_URL,
  DATA_MODE,
  MOCK_LATENCY_MS,
} from "./dataSource";
import type {
  AnalyticsResult,
  DataQualityResult,
  DataStatus,
  IndexTimeseriesPoint,
  RecommendedRoutesFile,
} from "../types";

import analyticsFixture from "./fixtures/analytics.json";
import timeseriesFixture from "./fixtures/index_timeseries.json";
import routesFixture from "./fixtures/recommended_routes.json";
import dataQualityFixture from "./fixtures/data_quality.json";

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`API ${path} responded ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

// --- endpoints ---------------------------------------------------------------
// The `api` branches are placeholders; the backend team owns the final paths.
// See docs note in getDataStatus() for what the API must additionally provide.

export function getAnalytics(): Promise<AnalyticsResult> {
  if (DATA_MODE === "api") return apiGet<AnalyticsResult>("/api/analytics");
  return delay(analyticsFixture as unknown as AnalyticsResult);
}

export function getTimeseries(): Promise<IndexTimeseriesPoint[]> {
  if (DATA_MODE === "api") return apiGet<IndexTimeseriesPoint[]>("/api/index/timeseries");
  return delay(timeseriesFixture as unknown as IndexTimeseriesPoint[]);
}

export function getRecommendedRoutes(): Promise<RecommendedRoutesFile> {
  if (DATA_MODE === "api") return apiGet<RecommendedRoutesFile>("/api/routes/recommended");
  return delay(routesFixture as unknown as RecommendedRoutesFile);
}

export function getDataQuality(): Promise<DataQualityResult> {
  if (DATA_MODE === "api") return apiGet<DataQualityResult>("/api/data-quality");
  return delay(dataQualityFixture as unknown as DataQualityResult);
}

/**
 * Provenance of the current figures.
 *
 * TODO(backend/scraper team): expose this as a real field on the analytics
 * response — `{ level: "LIVE" | "PUBLIC" | "SYNTHETIC", label, detail, as_of }`.
 * Until then it is derived here: airfare observations are synthetic, so the
 * whole index is a demonstration of the pipeline, not a measurement.
 */
export async function getDataStatus(): Promise<DataStatus> {
  const analytics = await getAnalytics();
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
