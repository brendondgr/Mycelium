import * as React from "react";

import { cn } from "@/lib/utils";

type SectionHeaderProps = {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Optional trailing element (e.g. a "New project" button). */
  action?: React.ReactNode;
  className?: string;
};

/** The scholarly Fraunces page title + supporting line atop each section. */
export function SectionHeader({
  title,
  subtitle,
  action,
  className,
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "mb-5 flex flex-wrap items-end justify-between gap-4",
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text-primary)]">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
