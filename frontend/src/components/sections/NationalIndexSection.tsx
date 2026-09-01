import type { AnalyticsResult, IndexTimeseriesPoint } from "../../types";
import { SectionHeader } from "../layout/SectionHeader";
import { IndexHero } from "./IndexHero";
import { IndexTrend } from "./IndexTrend";

interface NationalIndexSectionProps {
  analytics: AnalyticsResult;
  timeseries: IndexTimeseriesPoint[] | null;
}

export function NationalIndexSection({
  analytics,
  timeseries,
}: NationalIndexSectionProps) {
  return (
    <section>
      <SectionHeader
        index={1}
        title="National Airfare Price Index"
        description="One number per month tracking how expensive it is, on a weighted basket of routes, to fly domestically in India relative to the base period."
      />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <IndexHero priceIndex={analytics.price_index} />
        <IndexTrend data={timeseries ?? []} />
      </div>
    </section>
  );
}
