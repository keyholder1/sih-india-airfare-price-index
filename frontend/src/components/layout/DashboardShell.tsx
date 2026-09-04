import type { ReactNode } from "react";
import type { DataStatus } from "../../types";
import { DataStatusBadge } from "./DataStatusBadge";
import { AuthControl } from "./AuthControl";

interface DashboardShellProps {
  status: DataStatus | null;
  children: ReactNode;
}

export function DashboardShell({ status, children }: DashboardShellProps) {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-30 border-b border-hairline bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-baseline gap-3">
            <span className="text-sm font-semibold tracking-tight text-ink">
              Airfare&nbsp;Price&nbsp;Index
            </span>
            <span className="hidden text-xs text-ink-faint sm:inline">
              India · experimental CPI-augmentation prototype
            </span>
          </div>
          <div className="flex items-center gap-3">
            {status && <DataStatusBadge status={status} size="sm" />}
            <AuthControl />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1180px] px-6 pb-24 pt-8">
        <div className="mb-10">
          <p className="eyebrow">Smart India Hackathon · Real-time Airfare Price Index</p>
          <h1 className="mt-2 max-w-3xl text-2xl font-semibold leading-snug tracking-tight text-ink sm:text-[1.7rem]">
            Turning millions of scattered airfares into one auditable measure of
            how fast flying is getting more expensive.
          </h1>
        </div>
        {children}
      </main>

      <footer className="border-t border-hairline">
        <div className="mx-auto max-w-[1180px] px-6 py-6 text-xs leading-relaxed text-ink-faint">
          <p>
            Base period pinned to index&nbsp;=&nbsp;100. National index aggregates
            route-level price relatives using DGCA passenger-traffic-derived
            weights (real data). Methodology owned by the statistics engine; this
            dashboard visualises its output and performs no calculations of its own.
          </p>
          <p className="mt-1.5">
            DGCA passenger traffic, route metadata and coordinates are real /
            public data. {status ? status.detail : "Airfare observation provenance is labelled above."}
          </p>
        </div>
      </footer>
    </div>
  );
}
