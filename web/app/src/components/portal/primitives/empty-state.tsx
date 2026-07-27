import * as React from "react";

import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon?: React.ReactNode;
  /** Small uppercase eyebrow, e.g. "Coming soon". */
  badge?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
};

/**
 * The honest stand-in for a section whose pipeline does not exist yet (Daily
 * Reports, Opportunities, Deadlines, Reports) or a populated section with no data
 * for this account. Calm, on-brand, and clearly labeled — never fabricated data.
 */
export function EmptyState({
  icon,
  badge,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <section
      className={cn(
        "rounded-2xl border border-dashed border-border bg-surface px-8 py-14 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="mx-auto mb-4 flex h-[60px] w-[60px] items-center justify-center rounded-2xl bg-surface-alt text-brand-secondary">
          {icon}
        </div>
      ) : null}
      {badge ? (
        <span className="mb-3.5 inline-block rounded-full border border-dashed border-border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          {badge}
        </span>
      ) : null}
      <h2 className="font-serif text-xl font-semibold text-[var(--text-primary)]">
        {title}
      </h2>
      {description ? (
        <p className="mx-auto mt-2 max-w-[46ch] text-sm leading-relaxed text-[var(--text-secondary)]">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </section>
  );
}
