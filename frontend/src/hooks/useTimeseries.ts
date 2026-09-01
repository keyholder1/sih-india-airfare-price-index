import { getTimeseries } from "../data/client";
import type { IndexTimeseriesPoint } from "../types";
import { useAsync } from "./useAsync";

export function useTimeseries() {
  return useAsync<IndexTimeseriesPoint[]>(getTimeseries, []);
}
