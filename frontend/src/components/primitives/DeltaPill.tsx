import clsx from "clsx";
import { directionArrow, formatSignedPct } from "../../utils/format";

interface DeltaPillProps {
  /** percentage-point change, or null when the engine could not compute it */
  value: number | null;
  label?: string;
  size?: "sm" | "md";
  /** what a null value should read as */
  nullText?: string;
}

/**
 * Colour convention: airfares rising (index up) is shown in `rise`,
 * airfares falling in `fall`. A null change (e.g. YoY with no 12-month
 * history) is shown neutrally, never as zero.
 */
export function DeltaPill({
  value,
  label,
  size = "md",
  nullText = "n/a",
}: DeltaPillProps) {
  const isNull = value == null || Number.isNaN(value);
  const rising = !isNull && (value as number) > 0;
  const falling = !isNull && (value as number) < 0;

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border font-medium tabular",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        isNull && "border-hairline bg-surface-sunken text-ink-faint",
        rising && "border-rise/20 bg-rise-wash text-rise",
        falling && "border-fall/20 bg-fall-wash text-fall",
        !isNull && !rising && !falling && "border-hairline bg-surface-sunken text-ink-muted",
      )}
    >
      {label && <span className="text-[0.7em] font-semibold uppercase tracking-wide opacity-70">{label}</span>}
      {!isNull && <span aria-hidden>{directionArrow(value)}</span>}
      <span>{isNull ? nullText : formatSignedPct(value)}</span>
    </span>
  );
}
