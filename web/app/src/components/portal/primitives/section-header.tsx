import * as React from "react";

import { cn } from "@/lib/utils";

type SectionHeaderProps = {
  /**
   * Small uppercase label above the title, naming the kind of surface this is
   * ("Feed", "Opportunities", "Workspace"). Matches the eyebrow the public site
   * puts above every section heading, so a reader arriving from the marketing
   * pages finds the same hierarchy inside the product.
   */
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Optional trailing element (e.g. a "New project" button). */
  action?: React.ReactNode;
  className?: string;
};

/** The scholarly Fraunces page title + supporting line atop each section. */
export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  action,
  className,
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-[var(--divider)] pb-5",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? (
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--brand-primary-hover)]">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text-primary)]">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">
            {subtitle}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
