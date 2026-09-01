import { getAnalytics, getDataStatus } from "../data/client";
import type { AnalyticsResult, DataStatus } from "../types";
import { useAsync } from "./useAsync";

export function useAnalytics() {
  return useAsync<AnalyticsResult>(getAnalytics, []);
}

export function useDataStatus() {
  return useAsync<DataStatus>(getDataStatus, []);
}
