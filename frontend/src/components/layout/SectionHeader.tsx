interface SectionHeaderProps {
  index: number;
  title: string;
  description?: string;
}

export function SectionHeader({ index, title, description }: SectionHeaderProps) {
  return (
    <div className="mb-5 flex items-start gap-3.5">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-hairline-strong bg-surface text-xs font-semibold tabular text-ink-muted">
        {index}
      </span>
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
        {description && (
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-muted">
            {description}
          </p>
        )}
      </div>
    </div>
  );
}
