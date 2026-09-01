/**
 * Single switch between local fixtures and the real backend API.
 *
 *   MODE = "mock"  →  bundled JSON produced by the statistics engine
 *   MODE = "api"   →  HTTP calls to the backend (endpoints TBD by backend team)
 *
 * When the API lands, flip MODE (or set VITE_DATA_MODE=api) and fill in the
 * endpoint paths in client.ts. No component changes required — every client
 * function returns the same typed shape in both modes.
 */
export type DataMode = "mock" | "api";

const envMode = import.meta.env.VITE_DATA_MODE as DataMode | undefined;

export const DATA_MODE: DataMode = envMode ?? "mock";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

/** Simulated latency in mock mode so loading/entrance states are exercised. */
export const MOCK_LATENCY_MS = 260;
