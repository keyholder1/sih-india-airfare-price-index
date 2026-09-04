import { useState } from "react";
import { DashboardShell } from "./components/layout/DashboardShell";
import { Loading, ErrorState } from "./components/primitives/Loading";
import { NationalIndexSection } from "./components/sections/NationalIndexSection";
import { IndexContributionSection } from "./components/sections/IndexContributionSection";
import { RouteIntelligenceSection } from "./components/sections/RouteIntelligenceSection";
import { DataQualitySection } from "./components/sections/DataQualitySection";
import { RiskGeographySection } from "./components/sections/RiskGeographySection";
import { NewsContextSection } from "./components/sections/NewsContextSection";
import { ForecastSection } from "./components/sections/ForecastSection";
import { RouteLookupSection } from "./components/sections/RouteLookupSection";
import { useAnalytics, useDataStatus } from "./hooks/useAnalytics";
import { useTimeseries } from "./hooks/useTimeseries";
import { useDataQuality } from "./hooks/useDataQuality";
import type { ScrapeJobResult } from "./types";

export default function App() {
  // Bumped after Section 8's on-demand pipeline finishes a run (cache hit
  // or fresh scrape) so the rest of the dashboard -- National Index, Route
  // Intelligence, Data Quality -- refetches and reflects the newly
  // persisted/updated route instead of staying frozen at initial page load.
  const [dataVersion, setDataVersion] = useState(0);

  const analytics = useAnalytics(dataVersion);
  const timeseries = useTimeseries(dataVersion);
  const dataStatus = useDataStatus(dataVersion);
  const dataQuality = useDataQuality(dataVersion);

  // Single source of truth for the selected route — shared by the
  // contribution chart (Section 2), Route Intelligence (Section 3), and
  // News & event context (Section 6).
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);

  // The last on-demand pipeline result whose route isn't one of the
  // tracked/weighted routes -- so Route Intelligence can draw it on the
  // map/table too instead of it only ever showing in Section 8's own
  // results panel. Cleared isn't needed: buildAdHocRouteDetail already
  // no-ops once a route becomes tracked, and a newer run just replaces it.
  const [adHocResult, setAdHocResult] = useState<ScrapeJobResult | null>(null);

  return (
    <DashboardShell status={dataStatus.data}>
      {analytics.loading && !analytics.data && <Loading />}
      {analytics.error && <ErrorState error={analytics.error} />}
      {analytics.data && (
        <div className="space-y-14">
          <NationalIndexSection
            analytics={analytics.data}
            timeseries={timeseries.data}
          />
          <IndexContributionSection
            analytics={analytics.data}
            timeseries={timeseries.data}
            selectedRoute={selectedRoute}
            onRouteSelect={setSelectedRoute}
          />
          <RouteIntelligenceSection
            analytics={analytics.data}
            selectedRoute={selectedRoute}
            onRouteSelect={setSelectedRoute}
            adHocResult={adHocResult}
          />
          <DataQualitySection quality={dataQuality.data} loading={dataQuality.loading} />
          <RiskGeographySection analytics={analytics.data} />
          <NewsContextSection selectedRoute={selectedRoute} />
          <ForecastSection refreshKey={dataVersion} />
          <RouteLookupSection
            onComplete={(result) => {
              setDataVersion((v) => v + 1);
              setSelectedRoute(result.route);
              setAdHocResult(result);
            }}
          />
        </div>
      )}
    </DashboardShell>
  );
}
