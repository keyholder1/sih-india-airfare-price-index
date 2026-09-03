import clsx from "clsx";
import { HEAT_METRICS, type HeatMetric } from "../../utils/heat";

interface MetricToggleProps {
  value: HeatMetric;
  onChange: (metric: HeatMetric) => void;
}

/** Segmented control choosing which engine metric colours the heatmap. */
export function MetricToggle({ value, onChange }: MetricToggleProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Heatmap metric"
      className="inline-flex rounded-lg border border-hairline bg-surface-sunken p-0.5"
    >
      {HEAT_METRICS.map((m) => {
        const active = m.key === value;
        return (
          <button
            key={m.key}
            type="button"
            role="radio"
            aria-checked={active}
            title={m.hint}
            onClick={() => onChange(m.key)}
            className={clsx(
              "rounded-md px-2.5 py-1 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
              active
                ? "bg-surface text-ink shadow-sm"
                : "text-ink-faint hover:text-ink-muted",
            )}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
