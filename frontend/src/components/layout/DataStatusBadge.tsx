import clsx from "clsx";
import type { DataStatus } from "../../types";
import { formatPeriod } from "../../utils/format";

interface DataStatusBadgeProps {
  status: DataStatus;
  size?: "sm" | "md";
}

/**
 * Always-visible provenance marker. Judges (and anyone reading this later)
 * must never mistake the synthetic demonstration figures for a real
 * measurement of Indian airfare inflation.
 */
export function DataStatusBadge({ status, size = "md" }: DataStatusBadgeProps) {
  const isSynthetic = status.level === "SYNTHETIC";

  return (
    <span
      className={clsx(
        "group relative inline-flex items-center gap-2 rounded-full border font-semibold uppercase tracking-[0.1em]",
        size === "sm" ? "px-2.5 py-1 text-[0.62rem]" : "px-3 py-1.5 text-[0.68rem]",
        isSynthetic
          ? "border-synth-border bg-synth-wash text-synth"
          : "border-fall/30 bg-fall-wash text-fall",
      )}
    >
      <span
        className={clsx(
          "h-1.5 w-1.5 rounded-full",
          isSynthetic ? "bg-synth" : "bg-fall",
        )}
      />
      {isSynthetic ? "Demonstration / synthetic data" : status.label}
      <span className="font-medium normal-case tracking-normal opacity-70">
        · {formatPeriod(status.asOf)}
      </span>

      <span
        role="tooltip"
        className="pointer-events-none absolute right-0 top-full z-20 mt-2 w-72 rounded-lg border border-hairline bg-surface p-3 text-[0.72rem] font-normal normal-case leading-relaxed tracking-normal text-ink-muted opacity-0 shadow-panel-hover transition-opacity duration-150 group-hover:opacity-100"
      >
        {status.detail}
      </span>
    </span>
  );
}
