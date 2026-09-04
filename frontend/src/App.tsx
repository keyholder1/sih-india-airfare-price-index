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

export default function App() {
  const analytics = useAnalytics();
  const timeseries = useTimeseries();
  const dataStatus = useDataStatus();
  const dataQuality = useDataQuality();

  // Single source of truth for the selected route — shared by the
  // contribution chart (Section 2), Route Intelligence (Section 3), and
  // News & event context (Section 6).
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);

  return (
    <DashboardShell status={dataStatus.data}>
      {analytics.loading && <Loading />}
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
          />
          <DataQualitySection quality={dataQuality.data} loading={dataQuality.loading} />
          <RiskGeographySection analytics={analytics.data} />
          <NewsContextSection selectedRoute={selectedRoute} />
          <ForecastSection />
          <RouteLookupSection />
        </div>
      )}
    </DashboardShell>
  );
}
