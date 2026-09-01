import { useState } from "react";
import { DashboardShell } from "./components/layout/DashboardShell";
import { Loading, ErrorState } from "./components/primitives/Loading";
import { NationalIndexSection } from "./components/sections/NationalIndexSection";
import { IndexContributionSection } from "./components/sections/IndexContributionSection";
import { RouteIntelligenceSection } from "./components/sections/RouteIntelligenceSection";
import { useAnalytics, useDataStatus } from "./hooks/useAnalytics";
import { useTimeseries } from "./hooks/useTimeseries";

export default function App() {
  const analytics = useAnalytics();
  const timeseries = useTimeseries();
  const dataStatus = useDataStatus();

  // Single source of truth for the selected route — shared by the
  // contribution chart (Section 2) and Route Intelligence (Section 3).
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
          {/* Sections 4–5 land in the next steps. */}
        </div>
      )}
    </DashboardShell>
  );
}
