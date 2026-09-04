import { getForecast } from "../data/client";
import type { ForecastPayload } from "../types";
import { useAsync } from "./useAsync";

export function useForecast(refreshKey: unknown = 0) {
  return useAsync<ForecastPayload>(getForecast, [refreshKey]);
}
