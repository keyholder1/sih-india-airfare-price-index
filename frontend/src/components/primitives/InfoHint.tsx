import { useEffect, useId, useRef, useState } from "react";
import clsx from "clsx";

interface InfoHintProps {
  text: string;
  className?: string;
  /** Popover alignment relative to the trigger -- "center" (default) can
   *  clip near a page edge; use "left"/"right" for labels close to one. */
  align?: "center" | "left" | "right";
}

/** Small "?" trigger + click-toggle popover, for explaining one jargon
 *  label in plain English inline -- meant for a judge exploring the
 *  dashboard unaided, without a presenter narrating every term. Click
 *  (not hover) so it works the same on a trackpad during a live demo;
 *  closes on outside click or Escape. */
export function InfoHint({ text, className, align = "center" }: InfoHintProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={wrapRef} className={clsx("relative inline-flex align-middle", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border border-hairline-strong bg-surface-sunken text-[0.6rem] font-bold leading-none text-ink-faint transition-colors hover:border-brand hover:text-brand focus:outline-none focus:ring-1 focus:ring-brand"
      >
        ?
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={clsx(
            "absolute top-full z-30 mt-1.5 w-60 rounded-md border border-hairline-strong bg-surface p-2.5 text-[0.72rem] font-normal leading-snug normal-case tracking-normal text-ink-muted shadow-lg",
            align === "center" && "left-1/2 -translate-x-1/2",
            align === "left" && "left-0",
            align === "right" && "right-0"
          )}
        >
          {text}
        </span>
      )}
    </span>
  );
}
