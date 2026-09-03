import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { IndexTimeseriesPoint } from "../../types";
import { chart, INDEX_BASELINE } from "../../theme/tokens";
import {
  formatIndex,
  formatPeriod,
  formatSignedPct,
} from "../../utils/format";

interface LineIndexChartProps {
  data: IndexTimeseriesPoint[];
  height?: number;
}

interface TooltipEntry {
  payload: IndexTimeseriesPoint;
}

function IndexTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-hairline bg-surface px-3 py-2 text-xs shadow-panel-hover">
      <p className="font-semibold text-ink">{formatPeriod(point.period)}</p>
      <p className="mt-1 tabular text-ink-muted">
        Index <span className="font-semibold text-ink">{formatIndex(point.national_index)}</span>
      </p>
      <p className="tabular text-ink-muted">
        MoM{" "}
        <span
          className={
            (point.mom_change_pct ?? 0) >= 0 ? "text-rise" : "text-fall"
          }
        >
          {formatSignedPct(point.mom_change_pct)}
        </span>
      </p>
    </div>
  );
}

export function LineIndexChart({ data, height = 240 }: LineIndexChartProps) {
  const values = data
    .map((d) => d.national_index)
    .filter((v): v is number => v != null);
  const dataMin = values.length ? Math.min(...values) : INDEX_BASELINE;
  const dataMax = values.length ? Math.max(...values) : INDEX_BASELINE;
  const lower = Math.floor(Math.min(dataMin, INDEX_BASELINE) - 1.5);
  const upper = Math.ceil(dataMax + 1.5);

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
          <defs>
            <linearGradient id="indexFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={chart.brandSoft} stopOpacity={0.16} />
              <stop offset="100%" stopColor={chart.brandSoft} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={chart.hairline} vertical={false} />
          <XAxis
            dataKey="period"
            tickFormatter={formatPeriod}
            tick={{ fill: chart.inkFaint, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: chart.hairline }}
            dy={6}
          />
          <YAxis
            domain={[lower, upper]}
            tick={{ fill: chart.inkFaint, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <ReferenceLine
            y={INDEX_BASELINE}
            stroke={chart.baseline}
            strokeDasharray="4 4"
            label={{
              value: "Base = 100",
              position: "insideBottomRight",
              fill: chart.inkFaint,
              fontSize: 10,
            }}
          />
          <Tooltip content={<IndexTooltip />} cursor={{ stroke: chart.hairlineStrong }} />
          <Area
            type="monotone"
            dataKey="national_index"
            stroke={chart.brand}
            strokeWidth={2}
            fill="url(#indexFill)"
            dot={{ r: 2.5, fill: chart.brand, strokeWidth: 0 }}
            activeDot={{ r: 4, fill: chart.brand }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
