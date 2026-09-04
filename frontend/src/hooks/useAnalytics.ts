import { getAnalytics, getDataStatus } from "../data/client";
import type { AnalyticsResult, DataStatus } from "../types";
import { useAsync } from "./useAsync";

/** `refreshKey` -- bump it (see App.tsx's dataVersion) to refetch, e.g.
 *  after the on-demand route pipeline (Section 8) persists new data. */
export function useAnalytics(refreshKey: unknown = 0) {
  return useAsync<AnalyticsResult>(getAnalytics, [refreshKey]);
}

export function useDataStatus(refreshKey: unknown = 0) {
  return useAsync<DataStatus>(getDataStatus, [refreshKey]);
}
