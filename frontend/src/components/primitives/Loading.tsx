interface LoadingProps {
  label?: string;
}

export function Loading({ label = "Loading index data…" }: LoadingProps) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-ink-faint">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-hairline-strong border-t-brand" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="mx-auto max-w-md rounded-panel border border-rise/30 bg-rise-wash p-6 text-sm text-rise">
      <p className="font-semibold">Could not load dashboard data</p>
      <p className="mt-1 text-rise/80">{error.message}</p>
    </div>
  );
}
