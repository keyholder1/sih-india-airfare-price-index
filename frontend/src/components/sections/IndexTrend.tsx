import type { IndexTimeseriesPoint } from "../../types";
import { Panel } from "../primitives/Panel";
import { LineIndexChart } from "../charts/LineIndexChart";
import { formatPeriod } from "../../utils/format";

interface IndexTrendProps {
  data: IndexTimeseriesPoint[];
}

export function IndexTrend({ data }: IndexTrendProps) {
  const first = data[0];
  const last = data[data.length - 1];

  return (
    <Panel className="flex h-full flex-col p-6">
      <div className="mb-2 flex items-baseline justify-between">
        <p className="eyebrow">Index trend</p>
        {first && last && (
          <p className="text-xs text-ink-faint">
            {formatPeriod(first.period)} – {formatPeriod(last.period)}
          </p>
        )}
      </div>

      {data.length > 1 ? (
        <LineIndexChart data={data} height={248} />
      ) : (
        <p className="flex flex-1 items-center justify-center text-sm text-ink-faint">
          Not enough periods yet for a trend line.
        </p>
      )}

      <p className="mt-3 text-xs leading-relaxed text-ink-faint">
        Each point is the national index recomputed for that month by the
        statistics engine from the same observation set.
      </p>
    </Panel>
  );
}
