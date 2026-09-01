import { useEffect, useRef, useState } from "react";

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Dependency-free count-up for hero metrics. Respects
 * prefers-reduced-motion. Returns the animated value; callers format it.
 */
export function useCountUp(target: number | null, durationMs = 900): number {
  const [value, setValue] = useState(target ?? 0);
  const frame = useRef<number>();
  const startValue = useRef(0);

  useEffect(() => {
    if (target == null) return;

    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || durationMs <= 0) {
      setValue(target);
      return;
    }

    startValue.current = value;
    const from = startValue.current;
    const delta = target - from;
    const start = performance.now();

    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      setValue(from + delta * easeOutCubic(progress));
      if (progress < 1) frame.current = requestAnimationFrame(tick);
    };

    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
    // Re-run only when the target changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);

  return target == null ? 0 : value;
}
