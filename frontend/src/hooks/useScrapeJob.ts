import { useCallback, useEffect, useRef, useState } from "react";
import { createScrapeJob, getScrapeJob } from "../data/client";
import type { ScrapeJob } from "../types";

const POLL_INTERVAL_MS = 1500;
/** A single dropped/timed-out poll request (bad wifi, a momentary
 *  backend hiccup) must not kill the whole loop while the job itself is
 *  still genuinely running server-side -- retry with backoff first, and
 *  only surface a hard error once this many *consecutive* poll attempts
 *  have failed. */
const MAX_CONSECUTIVE_POLL_FAILURES = 4;
const POLL_RETRY_BACKOFF_MS = 3000;

export interface UseScrapeJob {
  job: ScrapeJob | null;
  error: string | null;
  isRunning: boolean;
  /** true while silently retrying after a transient poll failure --
   *  the loop hasn't given up, but the last attempt didn't land. */
  retrying: boolean;
  start: (origin: string, destination: string) => void;
  /** Stops polling and clears state. Doubles as "cancel" while a job is
   *  running (the frontend simply stops watching -- the backend job may
   *  finish on its own, but nothing here depends on that) and as
   *  "clear" once it's done/failed. */
  reset: () => void;
}

/** Creates a scrape job, then polls it every 1.5s until it reaches a
 *  terminal state (done/failed). One real backend call to create, then
 *  plain polling -- no websocket needed for a job that runs for tens of
 *  seconds, not hours. */
export function useScrapeJob(): UseScrapeJob {
  const [job, setJob] = useState<ScrapeJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failureCountRef = useRef(0);

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
          failureCountRef.current = 0;
          setRetrying(false);
          setJob(current);
          if (current.status === "done" || current.status === "failed") {
            stopPolling();
            return;
          }
          timerRef.current = setTimeout(() => poll(jobId), POLL_INTERVAL_MS);
        })
        .catch((err: unknown) => {
          failureCountRef.current += 1;
          if (failureCountRef.current >= MAX_CONSECUTIVE_POLL_FAILURES) {
            setRetrying(false);
            setError(
              `Lost contact with the server after ${MAX_CONSECUTIVE_POLL_FAILURES} attempts: ${
                err instanceof Error ? err.message : String(err)
              }`
            );
            stopPolling();
            return;
          }
          // Transient failure -- keep the job's last-known state on
          // screen, flag that we're retrying, and try again shortly
          // rather than giving up on a job that may still be running.
          setRetrying(true);
          timerRef.current = setTimeout(() => poll(jobId), POLL_RETRY_BACKOFF_MS);
        });
    },
    [stopPolling]
  );

  const start = useCallback(
    (origin: string, destination: string) => {
      stopPolling();
      failureCountRef.current = 0;
      setRetrying(false);
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
    failureCountRef.current = 0;
    setRetrying(false);
    setJob(null);
    setError(null);
  }, [stopPolling]);

  const isRunning = job != null && job.status !== "done" && job.status !== "failed";

  return { job, error, retrying, isRunning, start, reset };
}
