import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalyticsResult } from "../../types";
import { useRecommendedRoutes } from "../../hooks/useRoutes";
import { buildRouteDetails, findRouteDetail } from "../../utils/routes";
import type { HeatMetric } from "../../utils/heat";
import { routeLabel } from "../../utils/format";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { RouteNetworkMap } from "../charts/RouteNetworkMap";
import { MetricToggle } from "../route/MetricToggle";
import { RouteTable } from "../route/RouteTable";
import { RouteDetailPanel } from "../route/RouteDetailPanel";

interface RouteIntelligenceSectionProps {
  analytics: AnalyticsResult;
  selectedRoute: string | null;
  onRouteSelect: (route: string | null) => void;
}

export function RouteIntelligenceSection({
  analytics,
  selectedRoute,
  onRouteSelect,
}: RouteIntelligenceSectionProps) {
  const recommended = useRecommendedRoutes();
  const sectionRef = useRef<HTMLDivElement>(null);
  const [heatMetric, setHeatMetric] = useState<HeatMetric>("mom");

  const routes = useMemo(
    () => buildRouteDetails(analytics, recommended.data),
    [analytics, recommended.data],
  );
  const selectedDetail = findRouteDetail(routes, selectedRoute);

  // Bring the section into view when a route is selected from elsewhere on
  // the page (e.g. the contribution chart above). Only scrolls when the
  // section is mostly off-screen, so selecting a row inside the section
  // never yanks the viewport.
  useEffect(() => {
    if (!selectedRoute || !sectionRef.current) return;
    const rect = sectionRef.current.getBoundingClientRect();
    const mostlyOffscreen =
      rect.top > window.innerHeight * 0.55 || rect.bottom < window.innerHeight * 0.25;
    if (!mostlyOffscreen) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    sectionRef.current.scrollIntoView({
      behavior: reduced ? "auto" : "smooth",
      block: "start",
    });
  }, [selectedRoute]);

  return (
    <section ref={sectionRef} className="scroll-mt-20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader
          index={3}
          title="Route intelligence"
          description="Explore how individual domestic routes are influencing the national airfare index."
        />
        {selectedDetail && (
          <button
            type="button"
            onClick={() => onRouteSelect(null)}
            className="inline-flex items-center gap-2 rounded-full border border-brand/20 bg-brand-wash px-3 py-1 text-xs font-semibold text-brand transition-colors hover:bg-accent-wash"
          >
            <span className="text-[0.62rem] font-bold uppercase tracking-[0.1em] text-brand/70">
              Selected route
            </span>
            {selectedDetail.originCity && selectedDetail.destinationCity
              ? `${selectedDetail.originCity} → ${selectedDetail.destinationCity}`
              : routeLabel(selectedDetail.route)}
            <span aria-hidden className="text-ink-faint">✕</span>
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        {/* A. route heatmap */}
        <Panel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Route heatmap · where fares are moving</p>
              <p className="mt-1 text-xs text-ink-faint">
                {routes.filter((r) => r.coords).length} routes across{" "}
                {new Set(routes.flatMap((r) => [r.origin, r.destination])).size}{" "}
                metros
                {recommended.loading && " · loading city names…"}
              </p>
            </div>
            <MetricToggle value={heatMetric} onChange={setHeatMetric} />
          </div>
          <div className="mt-3">
            <RouteNetworkMap
              routes={routes}
              metric={heatMetric}
              selectedRoute={selectedRoute}
              onRouteSelect={onRouteSelect}
            />
          </div>
        </Panel>

        {/* B. selected route detail */}
        <div className="lg:pt-9">
          <RouteDetailPanel
            route={selectedDetail}
            onClear={() => onRouteSelect(null)}
          />
        </div>
      </div>

      {/* route overview table */}
      <Panel className="mt-5 p-5">
        <div className="mb-3 flex items-baseline justify-between">
          <p className="eyebrow">Route overview</p>
          <p className="text-xs text-ink-faint">
            {routes.length} routes · sortable · click a row to inspect
          </p>
        </div>
        <RouteTable
          routes={routes}
          selectedRoute={selectedRoute}
          onRouteSelect={onRouteSelect}
        />
      </Panel>

      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-ink-faint">
        Route index, MoM, traffic weight, contribution, volatility and status are
        produced by the statistics engine and shown here unchanged. Traffic
        weight is a route&apos;s share of national domestic passenger traffic
        (DGCA-derived), not a CPI expenditure weight. YoY is unavailable until
        twelve months of history exist.{" "}
        <span className="font-medium text-synth">
          The heatmap colours reflect movements in synthetic demonstration
          airfares, not measured Indian airfare inflation.
        </span>
      </p>
    </section>
  );
}
