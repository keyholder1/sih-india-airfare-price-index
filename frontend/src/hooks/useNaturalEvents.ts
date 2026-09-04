import { getNaturalEvents } from "../data/client";
import type { NationalNaturalEventsResult } from "../types";
import { useAsync } from "./useAsync";

/** Compact national list of real NASA EONET events associated with a
 *  significant route movement -- see docs/eonet_context.md. */
export function useNaturalEvents(refreshKey: unknown = 0) {
  return useAsync<NationalNaturalEventsResult>(getNaturalEvents, [refreshKey]);
}
