"use client";

import { MyloGlyph } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { MarkdownProse } from "@/components/portal/primitives/markdown-prose";
import type { DailyBriefing } from "@/lib/portal/types";

/** Short "Mon D" label from an ISO timestamp (empty on a bad/absent value). */
export function formatBriefingWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * The written "Mylo Report" as a standalone card — the daily briefing's prose
 * zone, reused by the Daily page and by both the personal and lab overviews so
 * the report reads identically wherever it appears. Handles the loading, empty,
 * and fallback-origin states itself.
 */
export function MyloReportCard({
  data,
  isLoading,
  title = "Mylo Report",
  className,
  scrollable = false,
}: {
  data: DailyBriefing | undefined;
  isLoading?: boolean;
  title?: string;
  className?: string;
  /** Fill the parent cell's height and let the body scroll internally, keeping
   * the header fixed — so the overview's left column scrolls on its own (needs a
   * height-bounded parent, which the overview grid provides at `lg`). */
  scrollable?: boolean;
}) {
  if (isLoading) {
    return (
      <Card accent="primary-rule" className={`animate-pulse p-6 ${className ?? ""}`}>
        <span className="block h-3 w-28 rounded bg-surface-alt" />
        <span className="mt-4 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-2/3 rounded bg-surface-alt" />
      </Card>
    );
  }

  const body = (data?.briefing?.body ?? "").trim();
  const isFallback = data?.briefing?.origin === "fallback";
  const when = formatBriefingWhen(data?.generated_at ?? null);

  return (
    <Card
      accent="primary-rule"
      className={`flex flex-col p-6 ${scrollable ? "min-h-0 lg:h-full" : ""} ${className ?? ""}`}
    >
      <div className="mb-3 flex shrink-0 items-center gap-2">
        <MyloGlyph size={20} className="text-primary" aria-hidden="true" />
        <span className="text-[10.5px] font-semibold uppercase tracking-[.09em] text-primary">
          {title}
          {when ? ` · ${when}` : ""}
        </span>
      </div>

      <div className={scrollable ? "min-h-0 flex-1 overflow-y-auto pr-1" : undefined}>
        {body ? (
          <MarkdownProse text={body} />
        ) : (
          <p className="text-[15px] leading-relaxed text-[var(--text-secondary)]">
            Mylo has nothing to report yet today.
          </p>
        )}

        {isFallback ? (
          <p className="mt-4 text-xs text-[var(--text-secondary)]">
            Written from today&rsquo;s counts — Mylo&rsquo;s writer was offline when
            this ran.
          </p>
        ) : null}
      </div>
    </Card>
  );
}
