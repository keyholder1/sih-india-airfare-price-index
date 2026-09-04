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
  NationalNaturalEventsResult,
  RecommendedRoutesFile,
  RouteContext,
  ScrapeJob,
} from "../types";

import analyticsFixture from "./fixtures/analytics.json";
import timeseriesFixture from "./fixtures/index_timeseries.json";
import routesFixture from "./fixtures/recommended_routes.json";
import dataQualityFixture from "./fixtures/data_quality.json";

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

/** Default per-request timeout. Without this, a `fetch` with no
 *  AbortController has no timeout of its own -- a stalled connection
 *  (bad network, or the backend hanging) would leave a caller waiting
 *  indefinitely with no error and no way to recover. Matters most for
 *  Section 8's job-status polling, where an indefinitely-hung request
 *  would freeze the whole poll loop (see useScrapeJob.ts's retry logic,
 *  which depends on a request eventually failing rather than hanging).
 *  35s (not the original 20s): the analytics/timeseries/data-quality/
 *  forecast/natural-events endpoints each do real pandas computation
 *  over the live dataset, and a real concurrent page-load burst of all
 *  of them measured up to ~15s worst-case even with multiple backend
 *  worker processes -- 20s cut that margin too close and produced a
 *  real, reproduced "Could not load dashboard data" failure. */
const DEFAULT_TIMEOUT_MS = 35_000;

function withTimeout(ms: number): AbortSignal {
  return AbortSignal.timeout(ms);
}

async function apiGet<T>(path: string, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { headers, signal: withTimeout(timeoutMs) });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new Error(`API ${path} timed out after ${timeoutMs / 1000}s.`);
    }
    throw err;
  }
  if (!res.ok) {
    throw new Error(`API ${path} responded ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

async function apiPost<T>(path: string, body: unknown, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "Content-Type": "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: withTimeout(timeoutMs),
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new Error(`API ${path} timed out after ${timeoutMs / 1000}s.`);
    }
    throw err;
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `API ${path} responded ${res.status} ${res.statusText}`);
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
    natural_events: [],
    natural_events_status: "UNAVAILABLE",
    weather_origin: null,
    weather_destination: null,
    weather_status: "UNAVAILABLE",
  };
}

export function getRouteContext(route: string): Promise<RouteContext> {
  if (DATA_MODE === "api") return apiGet<RouteContext>(`/api/v1/routes/${route}/context`);
  return delay(mockRouteContext(route));
}

/**
 * Compact national list of real NASA EONET natural events associated
 * with a significant route movement -- GET /api/v1/analytics/events
 * (api/services/analytics_service.get_natural_events). No mock fixture
 * exists (added after the fixture set was frozen) -- mock mode returns
 * an honestly-empty, clearly-labelled result instead of a network call.
 */
function mockNaturalEvents(): NationalNaturalEventsResult {
  return { events: [], routes_with_significant_movement_checked: 0, status: "OK", data_source: "synthetic" };
}

export function getNaturalEvents(): Promise<NationalNaturalEventsResult> {
  if (DATA_MODE === "api") return apiGet<NationalNaturalEventsResult>("/api/v1/analytics/events");
  return delay(mockNaturalEvents());
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
    data_source: "SYNTHETIC",
  };
}

export function getForecast(): Promise<ForecastPayload> {
  if (DATA_MODE === "api") return apiGet<ForecastPayload>("/api/v1/analytics/forecast");
  return delay(mockForecast());
}

/**
 * Provenance of the current figures. Read directly from the backend's own
 * `data_source` field (api/services/analytics_service.py, sourced from
 * data_access.classify_provenance) -- never guessed client-side. A
 * non-null national_index says nothing about provenance: the engine
 * happily computes an index from synthetic data too.
 */
export async function getDataStatus(): Promise<DataStatus> {
  const analytics = await getAnalytics();
  const asOf = analytics.price_index.current_period;

  switch (analytics.data_source) {
    case "REAL":
      return {
        level: "LIVE",
        label: "Live fare data",
        detail: "Every airfare observation behind these figures was collected by the scraper, not fabricated.",
        asOf,
      };
    case "MIXED":
      return {
        level: "MIXED",
        label: "Mixed real + synthetic data",
        detail:
          "Some airfare observations behind these figures are real scraper output and some are " +
          "synthetic/demo. This dataset is not purely real, so these numbers are not a clean " +
          "measurement of Indian airfare inflation.",
        asOf,
      };
    case "UNAVAILABLE":
      return {
        level: "UNAVAILABLE",
        label: "No data available",
        detail: "No airfare observations were found to compute these figures from.",
        asOf,
      };
    case "SYNTHETIC":
    default:
      return {
        level: "SYNTHETIC",
        label: "Demonstration / synthetic data",
        detail:
          "Airfare observations behind these figures are synthetic. The statistical " +
          "pipeline, DGCA passenger-traffic weights and route metadata are real; the " +
          "fare values are not, and these numbers are not a measurement of Indian airfare inflation.",
        asOf,
      };
  }
}

/**
 * On-demand two-route pipeline: a real, live SerpApi call (api/routes/
 * scrape.py), not a simulation, and not available in mock mode -- there
 * is nothing to fake here without misrepresenting a real network call
 * that didn't happen.
 */
export function createScrapeJob(origin: string, destination: string): Promise<{ job_id: string }> {
  if (DATA_MODE !== "api") {
    return Promise.reject(
      new Error("On-demand route lookup needs a real backend (VITE_DATA_MODE=api) -- there's no mock version of a live SerpApi call.")
    );
  }
  return apiPost<{ job_id: string }>("/api/v1/scrape/jobs", { origin, destination });
}

export function getScrapeJob(jobId: string): Promise<ScrapeJob> {
  return apiGet<ScrapeJob>(`/api/v1/scrape/jobs/${jobId}`);
}
