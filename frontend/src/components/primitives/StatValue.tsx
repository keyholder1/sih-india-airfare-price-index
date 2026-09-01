import clsx from "clsx";
import { useCountUp } from "../../hooks/useCountUp";

interface StatValueProps {
  value: number | null;
  /** how to render the (animated) numeric value */
  format: (v: number | null) => string;
  size?: "hero" | "stat" | "inline";
  className?: string;
  animate?: boolean;
}

export function StatValue({
  value,
  format,
  size = "stat",
  className,
  animate = true,
}: StatValueProps) {
  const animated = useCountUp(animate ? value : null, animate ? 900 : 0);
  const display = value == null ? null : animate ? animated : value;

  return (
    <span
      className={clsx(
        "tabular font-semibold text-ink",
        size === "hero" && "text-hero-num",
        size === "stat" && "text-stat-num",
        size === "inline" && "text-base",
        className,
      )}
    >
      {format(display)}
    </span>
  );
}
