import { getTimeseries } from "../data/client";
import type { IndexTimeseriesPoint } from "../types";
import { useAsync } from "./useAsync";

export function useTimeseries(refreshKey: unknown = 0) {
  return useAsync<IndexTimeseriesPoint[]>(getTimeseries, [refreshKey]);
}
