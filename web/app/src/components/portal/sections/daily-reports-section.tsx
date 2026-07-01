"use client";

import * as React from "react";
import Link from "next/link";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { StatCard } from "@/components/portal/sections/stat-card";
import {
  ArrowRightIcon,
  DocumentIcon,
  ReportIcon,
  SparkleIcon,
  TargetIcon,
} from "@/components/portal/icons";
import { useDailyReport } from "@/lib/portal/hooks";
import { SECTION_ROUTES } from "@/lib/portal/routes";
import type { DailyReportSummary } from "@/lib/portal/types";

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function pct(value: number | null): string | null {
  return typeof value === "number" ? `${value}%` : null;
}

/** The link through to the full paper list — the day's papers live there now. */
function PapersLink({ count }: { count: number }) {
  return (
    <Link
      href={SECTION_ROUTES.papers}
      className="group mt-1 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
    >
      {count > 0
        ? `View all ${count} paper${count === 1 ? "" : "s"}`
        : "View research papers"}
      <ArrowRightIcon
        size={14}
        aria-hidden="true"
        className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
      />
    </Link>
  );
}

function SummaryView({ summary }: { summary: DailyReportSummary }) {
  return (
    <div className="space-y-5">
      <Card accent="primary-rule" className="p-5">
        <h2 className="font-serif text-xl font-semibold leading-snug text-[var(--text-primary)]">
          {summary.headline}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          Today&rsquo;s research digest, summarized. The full ranked list — each
          paper with its percent-match score and why it matters — lives on your
          Research Papers page.
        </p>
        <PapersLink count={summary.paper_count} />
      </Card>

      <div className="grid grid-cols-2 gap-[14px] lg:grid-cols-4">
        <StatCard
          icon={<DocumentIcon size={16} />}
          label="Papers today"
          value={summary.paper_count}
        />
        <StatCard
          icon={<SparkleIcon size={16} />}
          label="Strong matches"
          value={summary.strong_matches}
          sub="75%+ fit"
        />
        <StatCard
          icon={<TargetIcon size={16} />}
          label="Top match"
          value={pct(summary.top_match) ?? "—"}
        />
        <StatCard
          icon={<TargetIcon size={16} />}
          label="Average match"
          value={pct(summary.average_match) ?? "—"}
        />
      </div>

      {summary.themes.length > 0 ? (
        <Card className="p-5">
          <p className="mb-2.5 text-[12.5px] font-semibold text-[var(--text-secondary)]">
            Recurring themes
          </p>
          <div className="flex flex-wrap gap-2">
            {summary.themes.map((theme) => (
              <Pill key={theme} tone="primary">
                {theme}
              </Pill>
            ))}
          </div>
          {summary.sources.length > 0 ? (
            <p className="mt-3.5 text-xs text-[var(--text-muted)]">
              Sources: {summary.sources.join(", ")}
            </p>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

function SkeletonSummary() {
  return (
    <div className="space-y-5">
      <Card className="animate-pulse p-5">
        <span className="block h-5 w-2/3 rounded bg-surface-alt" />
        <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-1.5 block h-3 w-1/2 rounded bg-surface-alt" />
      </Card>
      <div className="grid grid-cols-2 gap-[14px] lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} className="animate-pulse p-[18px]">
            <span className="block h-3 w-20 rounded bg-surface-alt" />
            <span className="mt-3 block h-6 w-12 rounded bg-surface-alt" />
          </Card>
        ))}
      </div>
    </div>
  );
}

/**
 * The Daily Report: a summary of the day's research. It rolls up today's paper
 * suggestions (count, match strength, recurring themes) and links through to the
 * Research Papers page for the full ranked list. A later phase will grow this
 * into a structured synthesis across projects, deadlines, and lab context.
 */
export function DailyReportsSection() {
  const { data, isLoading, isError } = useDailyReport();
  const summary = data?.summary ?? null;

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Summarizing your day…";
    if (summary && summary.paper_count > 0) {
      const when = formatWhen(data?.generated_at ?? null);
      return when
        ? `Your research summary for ${when}.`
        : "Your research summary for today.";
    }
    return "A summary of your day's research, gathered every morning.";
  })();

  return (
    <div>
      <SectionHeader title="Daily Reports" subtitle={subtitle} />

      {isLoading ? (
        <SkeletonSummary />
      ) : isError ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          title="Couldn't load your daily report"
          description="Something went wrong summarizing your digest. Please try again in a moment."
        />
      ) : !summary || summary.paper_count === 0 ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          badge="Coming soon"
          title="Your first daily report is on its way"
          description="Once Milo's literature scan runs against your research profile, your morning summary — how many papers matched, how strongly, and the recurring themes — will appear here."
        />
      ) : (
        <SummaryView summary={summary} />
      )}
    </div>
  );
}
