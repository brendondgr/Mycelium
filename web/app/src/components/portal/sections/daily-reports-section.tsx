"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  MyloReportCard,
  formatBriefingWhen,
} from "@/components/portal/sections/mylo-report-card";
import { StatCard } from "@/components/portal/sections/stat-card";
import {
  ArrowRightIcon,
  BankIcon,
  ConferenceIcon,
  DocumentIcon,
  MembersIcon,
  MyloGlyph,
  ReportIcon,
} from "@/components/portal/icons";
import { usePortal, type SectionKey } from "@/components/portal/portal-context";
import { useDailyBriefing } from "@/lib/portal/hooks";
import type {
  BriefingCategory,
  BriefingShowcaseItem,
  DailyBriefing,
} from "@/lib/portal/types";

/** Stable display order + per-category label, icon, and destination section. */
const CATEGORY_ORDER: BriefingCategory[] = [
  "papers",
  "grants",
  "conferences",
  "fellowships",
];

const CATEGORY_META: Record<
  BriefingCategory,
  { label: string; icon: React.ReactNode; section: SectionKey }
> = {
  papers: { label: "Papers", icon: <DocumentIcon size={16} />, section: "papers" },
  grants: { label: "Grants", icon: <BankIcon size={16} />, section: "opportunities" },
  conferences: {
    label: "Conferences",
    icon: <ConferenceIcon size={16} />,
    section: "conferences",
  },
  fellowships: {
    label: "Fellowships",
    icon: <MembersIcon size={16} />,
    section: "fellowships",
  },
};

/** The watched categories in stable order (defensive against odd API order). */
function orderedCategories(data: DailyBriefing): BriefingCategory[] {
  return CATEGORY_ORDER.filter((c) => data.categories.includes(c));
}

/* -- Top-right zone: the numeric summaries ---------------------------------- */

function TodaySummaries({ data }: { data: DailyBriefing }) {
  const { goToSection } = usePortal();
  const categories = orderedCategories(data);

  return (
    <Card className="p-5 text-center">
      <p className="mb-3 text-[12.5px] font-semibold text-[var(--text-secondary)]">
        Today&rsquo;s summaries
      </p>
      {categories.length > 0 ? (
        <div className="grid grid-cols-2 gap-[14px]">
          {categories.map((category) => {
            const meta = CATEGORY_META[category];
            const total = data.counts[category] ?? 0;
            const newCount = data.new_counts?.[category];
            const hasNewCount = typeof newCount === "number";
            return (
              <StatCard
                key={category}
                align="center"
                icon={meta.icon}
                label={meta.label}
                value={hasNewCount ? newCount : total}
                sub={hasNewCount ? `New · of ${total} matched` : undefined}
                onClick={() => goToSection(meta.section)}
              />
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-[var(--text-muted)]">
          You aren&rsquo;t watching any categories yet.
        </p>
      )}
    </Card>
  );
}

/* -- Bottom-right zone: the top items per category -------------------------- */

function ShowcaseRow({ item }: { item: BriefingShowcaseItem }) {
  const hasMatch = typeof item.match_percent === "number";
  const body = (
    <span className="flex min-w-0 flex-1 items-start gap-2.5">
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-[13px] font-medium leading-snug text-[var(--text-primary)]">
          {item.title}
        </span>
        {item.deadline_date ? (
          <span className="mt-0.5 block text-[11.5px] text-[var(--text-muted)]">
            Deadline {item.deadline_date}
          </span>
        ) : null}
      </span>
      <span className="flex shrink-0 items-center gap-1.5">
        {item.is_new ? <Pill tone="accent">New</Pill> : null}
        {hasMatch ? <Pill tone="primary">{item.match_percent}%</Pill> : null}
      </span>
    </span>
  );

  const shared =
    "group flex w-full items-start rounded-xl border border-[var(--divider)] bg-surface-alt/40 px-3 py-2.5 text-left transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none";

  return item.url ? (
    <a href={item.url} target="_blank" rel="noopener noreferrer" className={shared}>
      {body}
    </a>
  ) : (
    <div className={shared}>{body}</div>
  );
}

function BriefingShowcase({ data }: { data: DailyBriefing }) {
  const { goToSection } = usePortal();
  const groups = orderedCategories(data)
    .map((category) => ({ category, items: data.showcase[category] ?? [] }))
    .filter((g) => g.items.length > 0);

  return (
    <Card className="p-5">
      <p className="mb-3 text-[12.5px] font-semibold text-[var(--text-secondary)]">
        Briefing showcase
      </p>
      {groups.length > 0 ? (
        <div className="space-y-4">
          {groups.map(({ category, items }) => {
            const meta = CATEGORY_META[category];
            return (
              <div key={category}>
                <button
                  type="button"
                  onClick={() => goToSection(meta.section)}
                  className="group mb-2 inline-flex items-center gap-1.5 rounded text-[11px] font-semibold uppercase tracking-[.07em] text-[var(--text-muted)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {meta.label}
                  <ArrowRightIcon
                    size={12}
                    aria-hidden="true"
                    className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
                  />
                </button>
                <div className="space-y-2">
                  {items.map((item) => (
                    <ShowcaseRow key={item.content_id} item={item} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-[var(--text-muted)]">
          No standout items today — check back after the next scan.
        </p>
      )}
    </Card>
  );
}

/* -- Skeleton --------------------------------------------------------------- */

function SkeletonReport() {
  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Card className="animate-pulse p-6 lg:col-span-3">
        <span className="block h-3 w-28 rounded bg-surface-alt" />
        <span className="mt-4 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-2/3 rounded bg-surface-alt" />
      </Card>
      <div className="flex flex-col gap-5 lg:col-span-2">
        <Card className="animate-pulse p-5">
          <span className="block h-3 w-24 rounded bg-surface-alt" />
          <div className="mt-3 grid grid-cols-2 gap-[14px]">
            {[0, 1, 2, 3].map((i) => (
              <span key={i} className="block h-16 rounded bg-surface-alt" />
            ))}
          </div>
        </Card>
        <Card className="animate-pulse p-5">
          <span className="block h-3 w-24 rounded bg-surface-alt" />
          <span className="mt-3 block h-10 w-full rounded bg-surface-alt" />
        </Card>
      </div>
    </div>
  );
}

/**
 * The Daily "Mylo Report": a three-zone briefing surface. The left zone is the
 * written cross-category briefing; the top-right zone is the day's numeric
 * summaries (only the categories the user watches); the bottom-right zone is the
 * showcase of top items the briefing is grounded in. On mobile the zones stack
 * briefing -> summaries -> showcase. Data comes from `GET /api/daily-briefing/`.
 */
export function DailyReportsSection() {
  const { data, isLoading, isError } = useDailyBriefing();
  const hasRun = Boolean(data && data.generated_at);

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering your briefing…";
    if (hasRun) {
      const when = formatBriefingWhen(data?.generated_at ?? null);
      return when
        ? `Mylo's research briefing for ${when}.`
        : "Mylo's research briefing for today.";
    }
    return "Mylo's daily research briefing, written for you every morning.";
  })();

  return (
    <div>
      <SectionHeader title="Daily Reports" subtitle={subtitle} />

      {isLoading ? (
        <SkeletonReport />
      ) : isError ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          title="Couldn't load your Mylo Report"
          description="Something went wrong loading today's briefing. Please try again in a moment."
        />
      ) : !hasRun || !data ? (
        <EmptyState
          icon={<MyloGlyph size={30} />}
          title="Your first Mylo Report is on its way"
          description="Once the daily run finishes scanning your watched topics, your morning briefing — a written summary, the day's counts, and the top items in each category — will appear here."
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-5">
          <MyloReportCard data={data} className="lg:col-span-3" />
          <div className="flex flex-col gap-5 lg:col-span-2">
            <TodaySummaries data={data} />
            <BriefingShowcase data={data} />
          </div>
        </div>
      )}
    </div>
  );
}
