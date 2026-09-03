import { getRouteContext } from "../data/client";
import type { RouteContext } from "../types";
import { useAsync } from "./useAsync";

/** Re-fetches whenever `route` changes; pass null to skip fetching. */
export function useRouteContext(route: string | null) {
  return useAsync<RouteContext | null>(
    () => (route ? getRouteContext(route) : Promise.resolve(null)),
    [route],
  );
}
