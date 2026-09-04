import { getDataQuality } from "../data/client";
import type { DataQualityResult } from "../types";
import { useAsync } from "./useAsync";

export function useDataQuality(refreshKey: unknown = 0) {
  return useAsync<DataQualityResult>(getDataQuality, [refreshKey]);
}
