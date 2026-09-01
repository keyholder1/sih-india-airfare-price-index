import clsx from "clsx";
import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
  /** subtle lift on hover — use for interactive panels only */
  interactive?: boolean;
  as?: "div" | "section" | "article";
}

export function Panel({ children, className, interactive, as = "div" }: PanelProps) {
  const Tag = as;
  return (
    <Tag
      className={clsx(
        "panel",
        interactive &&
          "transition-shadow duration-200 ease-out-soft hover:shadow-panel-hover",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
