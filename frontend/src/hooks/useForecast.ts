import { getForecast } from "../data/client";
import type { ForecastPayload } from "../types";
import { useAsync } from "./useAsync";

export function useForecast() {
  return useAsync<ForecastPayload>(getForecast, []);
}
