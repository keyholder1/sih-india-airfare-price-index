import { getDataQuality } from "../data/client";
import type { DataQualityResult } from "../types";
import { useAsync } from "./useAsync";

export function useDataQuality() {
  return useAsync<DataQualityResult>(getDataQuality, []);
}
