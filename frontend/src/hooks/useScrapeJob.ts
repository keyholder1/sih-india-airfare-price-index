import { useCallback, useEffect, useRef, useState } from "react";
import { createScrapeJob, getScrapeJob } from "../data/client";
import type { ScrapeJob } from "../types";

const POLL_INTERVAL_MS = 1500;

export interface UseScrapeJob {
  job: ScrapeJob | null;
  error: string | null;
  isRunning: boolean;
  start: (origin: string, destination: string) => void;
  reset: () => void;
}

/** Creates a scrape job, then polls it every 1.5s until it reaches a
 *  terminal state (done/failed). One real backend call to create, then
 *  plain polling -- no websocket needed for a job that runs for tens of
 *  seconds, not hours. */
export function useScrapeJob(): UseScrapeJob {
  const [job, setJob] = useState<ScrapeJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback(
    (jobId: string) => {
      getScrapeJob(jobId)
        .then((current) => {
          setJob(current);
          if (current.status === "done" || current.status === "failed") {
            stopPolling();
            return;
          }
          timerRef.current = setTimeout(() => poll(jobId), POLL_INTERVAL_MS);
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : String(err));
          stopPolling();
        });
    },
    [stopPolling]
  );

  const start = useCallback(
    (origin: string, destination: string) => {
      stopPolling();
      setError(null);
      setJob(null);
      createScrapeJob(origin, destination)
        .then(({ job_id: jobId }) => poll(jobId))
        .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    },
    [poll, stopPolling]
  );

  const reset = useCallback(() => {
    stopPolling();
    setJob(null);
    setError(null);
  }, [stopPolling]);

  const isRunning = job != null && job.status !== "done" && job.status !== "failed";

  return { job, error, isRunning, start, reset };
}
