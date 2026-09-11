"use client";

import * as React from "react";

import type { BriefingStats } from "@/lib/portal/types";

/**
 * What the run actually found, in the words the Discord post uses.
 *
 * The report's summary table says where today's arrivals landed. It cannot say
 * whether that was a heavy day filtered hard or a thin one scraped for whatever
 * was there — and that is the judgement a reader makes before deciding to read
 * on. This strip is the missing context: how much Mylo read, how much of it
 * matched, how much of that earned a place, and what is due soon.
 *
 * Every figure is read from the stored `stats` the nightly run settled, never
 * derived here, so this block and the Discord post cannot quote different
 * numbers for the same morning.
 *
 * Absence is rendered as absence. A briefing written before statistics existed
 * carries `{}` and this renders nothing; a corpus total the collector could not
 * answer is `null` and its clause is omitted, because "Mylo read 0 new papers"
 * and "Mylo does not know how many it read" are different statements and only
 * one of them is ever true.
 */

function formatCount(value: number): string {
  return value.toLocaleString();
}

/** "Mylo read 2,140 new papers and 186 opportunity updates." */
function volumeSentence(stats: BriefingStats): string | null {
  const clauses: string[] = [];
  if (typeof stats.discovered_papers === "number") {
    const noun = stats.discovered_papers === 1 ? "paper" : "papers";
    clauses.push(`${formatCount(stats.discovered_papers)} new ${noun}`);
  }
  if (typeof stats.discovered_opportunities === "number") {
    const noun = stats.discovered_opportunities === 1 ? "update" : "updates";
    clauses.push(`${formatCount(stats.discovered_opportunities)} opportunity ${noun}`);
  }
  return clauses.length ? `Mylo read ${clauses.join(" and ")}.` : null;
}

/** "41 matched you or your projects, 7 entered a top list, and 2 raised alerts." */
function selectivitySentence(stats: BriefingStats, subject: string): string {
  const matched = stats.matched ?? 0;
  const entered = stats.entered ?? 0;
  const alerts = stats.alerts ?? 0;
  const raised = alerts
    ? `${alerts} raised ${alerts === 1 ? "an alert" : "alerts"}`
    : "none raised alerts";
  return (
    `${formatCount(matched)} matched ${subject}, ` +
    `${formatCount(entered)} entered a top list, and ${raised}.`
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {label}
      </span>
      <span className="text-[12.5px] text-[var(--text-primary)]">{children}</span>
    </div>
  );
}

export function ReportStatistics({
  stats,
  subject = "you or your projects",
  className,
}: {
  stats: BriefingStats | undefined;
  /** Who the match was for — "the lab" on a lab report. */
  subject?: string;
  className?: string;
}) {
  if (!stats || Object.keys(stats).length === 0) return null;

  const volume = volumeSentence(stats);
  const byCategory = Object.entries(stats.by_category ?? {});
  const byTheme = stats.by_theme ?? [];
  const nearest = stats.nearest_deadline;
  const windowDays = stats.deadline_window_days ?? 14;

  return (
    <section
      className={`rounded-lg border border-[var(--border)] bg-surface-alt px-4 py-3 ${className ?? ""}`}
    >
      <h3 className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        What Mylo found
      </h3>
      <p className="text-[12.5px] leading-5 text-[var(--text-primary)]">
        {volume ? `${volume} ` : ""}
        {selectivitySentence(stats, subject)}
      </p>

      <div className="mt-2.5 space-y-1.5">
        {byCategory.length ? (
          <Row label="By category">
            {byCategory
              .map(([key, pair]) => {
                const [entered, inFeed] = pair ?? [0, 0];
                const label = key.charAt(0).toUpperCase() + key.slice(1);
                return `${label} ${entered} · ${inFeed}`;
              })
              .join("   ")}
          </Row>
        ) : null}
        {byTheme.length ? (
          <Row label="By theme">
            {byTheme.map(([label, count]) => `${label} ${count}`).join(" · ")}
          </Row>
        ) : null}
        <Row label={`Deadlines in ${windowDays} days`}>
          {stats.deadlines_in_window
            ? `${stats.deadlines_in_window}${
                nearest ? ` · nearest: ${nearest.title}, ${nearest.due_date}` : ""
              }`
            : "None."}
        </Row>
        {stats.private_projects_hidden ? (
          <Row label="Not shown">
            {`${stats.private_projects_hidden} private ${
              stats.private_projects_hidden === 1 ? "project" : "projects"
            }`}
          </Row>
        ) : null}
      </div>
      <p className="mt-2 text-[11px] text-[var(--text-muted)]">
        By category reads <span className="whitespace-nowrap">new · in your feeds</span>.
      </p>
    </section>
  );
}
