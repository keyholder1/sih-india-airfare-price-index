import { useRouteContext } from "../../hooks/useNewsContext";
import { SectionHeader } from "../layout/SectionHeader";
import { Panel } from "../primitives/Panel";
import { DeltaPill } from "../primitives/DeltaPill";
import { routeLabel } from "../../utils/format";

interface NewsContextSectionProps {
  selectedRoute: string | null;
}

/** Section 6: news/event context for the route selected elsewhere on the
 * page (Section 3's map/table or Section 2's contribution chart) -- "what
 * might explain this route's movement," never framed as causation (see
 * the backend's CAUSATION_DISCLAIMER). Every article here is fabricated
 * demo content (MockNewsProvider) explicitly labelled as such. */
export function NewsContextSection({ selectedRoute }: NewsContextSectionProps) {
  const context = useRouteContext(selectedRoute);

  return (
    <section className="scroll-mt-20">
      <SectionHeader
        index={6}
        title="News & event context"
        description="Potential factors behind a selected route's price movement -- contextual only, never used to compute the index."
      />

      {!selectedRoute && (
        <Panel className="p-6 text-center text-sm text-ink-faint">
          Select a route above (map, table, or contribution chart) to see what might explain its movement.
        </Panel>
      )}

      {selectedRoute && context.loading && (
        <Panel className="p-6 text-center text-sm text-ink-faint">Loading context for {routeLabel(selectedRoute)}…</Panel>
      )}

      {selectedRoute && context.data && (
        <Panel className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">{routeLabel(selectedRoute)}</p>
              <p className="mt-1 text-sm text-ink-muted">
                {context.data.significant_movement
                  ? "This route had a significant price movement."
                  : "No significant price movement to explain right now."}
              </p>
            </div>
            {context.data.movement_pct != null && (
              <DeltaPill value={context.data.movement_pct} label={context.data.movement_direction ?? undefined} />
            )}
          </div>

          {context.data.events.length === 0 ? (
            <p className="mt-4 text-sm text-ink-faint">No news/event matches for this route right now.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {context.data.events.map((event, i) => (
                <li key={i} className="rounded-lg border border-hairline p-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium text-ink">{event.headline}</p>
                    <span className="shrink-0 rounded-full border border-hairline bg-surface-sunken px-2 py-0.5 text-[0.62rem] font-semibold tabular text-ink-faint">
                      {(event.relevance_score * 100).toFixed(0)}% match
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-ink-faint">
                    {event.source} · {event.publication_date}
                  </p>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-4 text-xs leading-relaxed text-synth">
            {context.data.data_source === "real"
              ? "Live news search results -- relevance to this specific route's movement is a heuristic match, not a confirmed cause. Never used to compute the index itself."
              : "Demo news content (synthetic) -- fabricated for this project to exercise the matching logic, not real reporting. Never used to compute the index itself."}
          </p>
        </Panel>
      )}
    </section>
  );
}
