"use client";

import { MyloGlyph } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { MarkdownProse } from "@/components/portal/primitives/markdown-prose";
import { ReportStatistics } from "@/components/portal/primitives/report-statistics";
import { ReportSummaryTable } from "@/components/portal/primitives/report-summary-table";
import type { DailyBriefing } from "@/lib/portal/types";

/** Short "Mon D" label from an ISO timestamp (empty on a bad/absent value). */
export function formatBriefingWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * "Mon D, YYYY" from a `YYYY-MM-DD` day (the briefing's `generated_on`).
 *
 * Parsed field by field rather than through `new Date(day)`: that form is read as
 * UTC midnight, which renders as the *previous* day for anyone west of Greenwich.
 * Reports history is all dates, so an off-by-one there would be visible on every
 * row rather than an edge case.
 */
export function formatBriefingDay(day: string | null): string {
  if (!day) return "";
  const [y, m, d] = day.split("-").map(Number);
  if (!y || !m || !d) return "";
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
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
  statsSubject = "you or your projects",
  className,
  scrollable = false,
}: {
  data: DailyBriefing | undefined;
  isLoading?: boolean;
  title?: string;
  /** Who the statistics strip says the matches were for — "the lab" on a lab
   * overview, where "you or your projects" would name the wrong reader. */
  statsSubject?: string;
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
  const isCarried = data?.briefing?.origin === "carried";
  // The day the report covers, not the moment it was written: a same-day rerun
  // moves `generated_at`, and an archived day must be labelled by its own date.
  const when = data?.generated_on
    ? formatBriefingDay(data.generated_on)
    : formatBriefingWhen(data?.generated_at ?? null);

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
        {/* The report opens with its own map: what is new for the reader and for
            each project they are on. Above the prose, because it is what tells
            them whether the prose below is worth reading today. */}
        <ReportSummaryTable
          rows={data?.project_summary}
          categories={data?.categories ?? []}
          className="mb-4"
        />

        {/* And what those counts were drawn from. The table says where today's
            arrivals landed; this says whether that was a heavy day filtered hard
            or a thin one — the judgement a reader makes before reading on. */}
        <ReportStatistics
          stats={data?.stats}
          subject={statsSubject}
          className="mb-4"
        />

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
        {/* Nothing new reached the top 25, so yesterday's report still stands.
            Labelling it is the difference between "quiet day" and "the run
            broke" — an unlabelled repeat reads as the latter. */}
        {isCarried ? (
          <p className="mt-4 text-xs text-[var(--text-secondary)]">
            Nothing new reached your top lists today, so this is yesterday&rsquo;s
            report.
          </p>
        ) : null}
      </div>
    </Card>
  );
}
