import { getRecommendedRoutes } from "../data/client";
import type { RecommendedRoutesFile } from "../types";
import { useAsync } from "./useAsync";

export function useRecommendedRoutes() {
  return useAsync<RecommendedRoutesFile>(getRecommendedRoutes, []);
}
