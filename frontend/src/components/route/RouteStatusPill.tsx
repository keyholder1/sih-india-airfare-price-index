import clsx from "clsx";
import type { RouteStatus } from "../../types";

const LABELS: Record<RouteStatus, string> = {
  OK: "Active",
  NEW_ROUTE: "New route",
  DISCONTINUED: "Discontinued",
  NO_BASE_DATA: "No base data",
  INSUFFICIENT_DATA: "Insufficient data",
};

const TONE: Record<RouteStatus, string> = {
  OK: "border-status-ok/25 bg-fall-wash text-status-ok",
  NEW_ROUTE: "border-status-new/25 bg-accent-wash text-status-new",
  DISCONTINUED: "border-hairline-strong bg-surface-sunken text-status-discontinued",
  NO_BASE_DATA: "border-hairline-strong bg-surface-sunken text-status-discontinued",
  INSUFFICIENT_DATA: "border-synth-border bg-synth-wash text-synth",
};

interface RouteStatusPillProps {
  status: RouteStatus;
  size?: "sm" | "md";
}

export function RouteStatusPill({ status, size = "md" }: RouteStatusPillProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-[0.08em]",
        size === "sm" ? "px-2 py-0.5 text-[0.6rem]" : "px-2.5 py-1 text-[0.66rem]",
        TONE[status],
      )}
    >
      <span className="h-1 w-1 rounded-full bg-current" />
      {LABELS[status]}
    </span>
  );
}
