import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BookingHorizonVolatility } from "../../types";
import { chart } from "../../theme/tokens";
import { horizonLabel } from "../../utils/format";

interface BookingHorizonChartProps {
  data: BookingHorizonVolatility[];
  height?: number;
}

const BUCKET_ORDER = ["0-3", "4-7", "8-14", "15-30", "31-60", "61+"];

const CLASS_COLOR: Record<string, string> = {
  LOW: chart.fall,
  MODERATE: chart.synth,
  HIGH: chart.rise,
  INSUFFICIENT_DATA: chart.hairlineStrong,
};

function HorizonTooltip({ active, payload }: { active?: boolean; payload?: { payload: BookingHorizonVolatility }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-hairline bg-surface px-3 py-2 text-xs shadow-panel-hover">
      <p className="font-semibold text-ink">{horizonLabel(p.bucket)} before departure</p>
      <p className="mt-1 tabular text-ink-muted">
        Volatility{" "}
        <span className="font-semibold text-ink">{p.volatility == null ? "n/a" : p.volatility.toFixed(3)}</span>
      </p>
      <p className="text-ink-muted">{p.classification.replace("_", " ")} · {p.observations_used} observations</p>
    </div>
  );
}

/**
 * Coefficient-of-variation volatility by booking horizon -- a route can
 * have a flat index and still be wildly unpredictable booking to booking;
 * this is the second, genuinely different signal from the price index
 * itself (see docs/sih_pitch.md's "5 strongest things to tell judges").
 */
export function BookingHorizonChart({ data, height = 220 }: BookingHorizonChartProps) {
  const ordered = BUCKET_ORDER.map(
    (bucket) => data.find((d) => d.bucket === bucket) ?? { bucket, volatility: null, classification: "INSUFFICIENT_DATA", observations_used: 0 },
  );

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-faint">No booking-horizon data available for this period.</p>;
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={ordered} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
          <CartesianGrid stroke={chart.hairline} vertical={false} />
          <XAxis
            dataKey="bucket"
            tickFormatter={horizonLabel}
            tick={{ fill: chart.inkFaint, fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: chart.hairline }}
          />
          <YAxis tick={{ fill: chart.inkFaint, fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
          <Tooltip content={<HorizonTooltip />} cursor={{ fill: chart.hairline, opacity: 0.4 }} />
          <Bar dataKey="volatility" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {ordered.map((entry) => (
              <Cell key={entry.bucket} fill={CLASS_COLOR[entry.classification] ?? chart.hairlineStrong} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.68rem] text-ink-faint">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: chart.fall }} />Low</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: chart.synth }} />Moderate</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: chart.rise }} />High</span>
      </div>
    </div>
  );
}
