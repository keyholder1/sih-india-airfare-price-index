import { useMemo, useState } from "react";
import clsx from "clsx";
import type { InflationMatrix } from "../../types";
import { divergingColor } from "../../utils/heat";
import { formatSignedPct } from "../../utils/format";

interface InflationHeatmapProps {
  matrix: InflationMatrix;
  metric: "MoM" | "YoY";
}

/**
 * Origin x Destination grid — the actual heatmap docs/sih_pitch.md refers
 * to ("route-level inflation geography, missing != zero"), distinct from
 * the geographic route map above (Section 3). A blank cell is a route
 * with no data, rendered as blank, never coloured as zero movement.
 */
export function InflationHeatmap({ matrix, metric }: InflationHeatmapProps) {
  const [hovered, setHovered] = useState<{ o: string; d: string; v: number | null } | null>(null);

  const maxAbs = useMemo(() => {
    const magnitudes = matrix.values.flat().filter((v): v is number => v != null).map(Math.abs);
    return magnitudes.length ? Math.max(...magnitudes) : 1;
  }, [matrix]);

  if (matrix.origins.length === 0 || matrix.destinations.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-faint">No route pairs available for this period.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="border-separate" style={{ borderSpacing: 3 }}>
        <thead>
          <tr>
            <th className="w-12" />
            {matrix.destinations.map((d) => (
              <th
                key={d}
                className="pb-1 text-center text-[0.62rem] font-semibold uppercase tracking-wide text-ink-faint"
              >
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.origins.map((o, i) => (
            <tr key={o}>
              <th className="pr-2 text-right text-[0.62rem] font-semibold uppercase tracking-wide text-ink-faint">
                {o}
              </th>
              {matrix.destinations.map((d, j) => {
                const v = matrix.values[i]?.[j] ?? null;
                const isHovered = hovered?.o === o && hovered?.d === d;
                return (
                  <td key={d} className="p-0">
                    {o === d ? (
                      <div className="h-9 w-9 rounded-md bg-surface-sunken" />
                    ) : (
                      <button
                        type="button"
                        onMouseEnter={() => setHovered({ o, d, v })}
                        onMouseLeave={() => setHovered(null)}
                        className={clsx(
                          "h-9 w-9 rounded-md text-[0.6rem] font-semibold tabular transition-transform",
                          isHovered && "scale-110 ring-2 ring-accent/50",
                        )}
                        style={{ backgroundColor: v == null ? "transparent" : divergingColor(v, maxAbs) }}
                      >
                        {v == null ? (
                          <span className="text-ink-faint">·</span>
                        ) : (
                          <span className={Math.abs(v) / maxAbs > 0.55 ? "text-white" : "text-ink"}>
                            {v > 0 ? "+" : ""}
                            {v.toFixed(0)}
                          </span>
                        )}
                      </button>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-ink-faint">
        <p>
          {hovered
            ? hovered.v == null
              ? `${hovered.o} → ${hovered.d}: no data`
              : `${hovered.o} → ${hovered.d}: ${formatSignedPct(hovered.v)} ${metric}`
            : `Hover a cell for exact ${metric} % · rows = origin, columns = destination`}
        </p>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: divergingColor(-maxAbs, maxAbs) }} />
          <span>fell</span>
          <span className="h-2.5 w-2.5 rounded-sm bg-surface-sunken" />
          <span>flat</span>
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: divergingColor(maxAbs, maxAbs) }} />
          <span>rose</span>
        </div>
      </div>
    </div>
  );
}
