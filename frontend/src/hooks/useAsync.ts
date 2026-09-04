import { useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

/** Minimal data-fetching hook. One request per mount by default; pass a
 *  changing value in `deps` (e.g. a bumped "data version") to refetch
 *  later, such as after Section 8's on-demand pipeline persists new data.
 *  A refetch (any run after the first) keeps showing the previous `data`
 *  while `loading` is true, instead of clearing it -- callers gating a
 *  whole subtree on `data != null` (see App.tsx) would otherwise unmount
 *  and remount that subtree on every refresh, losing its local state. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    error: null,
  });
  const isFirstRun = useRef(true);

  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ data: isFirstRun.current ? null : prev.data, loading: true, error: null }));
    isFirstRun.current = false;

    fn()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState((prev) => ({
            data: prev.data,
            loading: false,
            error: error instanceof Error ? error : new Error(String(error)),
          }));
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
