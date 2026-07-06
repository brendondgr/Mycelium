"use client";

import * as React from "react";

import { usePortal, type SectionKey } from "@/components/portal/portal-context";
import { useDailyReport, useDeadlines, useProfile, useWatch } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";
import {
  ArrowRightIcon,
  CalendarIcon,
  DocumentIcon,
  FolderIcon,
  MembersIcon,
  TargetIcon,
} from "@/components/portal/icons";

import { Card } from "@/components/portal/primitives/card";
import { MatchBadge } from "@/components/portal/sections/opportunity-bits";
import { MyloSummaryCard } from "@/components/portal/sections/mylo-summary-card";
import { StatCard } from "@/components/portal/sections/stat-card";
import { NextActions } from "@/components/portal/sections/next-actions";
import { LabOverviewSection } from "@/components/portal/sections/lab-overview-section";
import { LabEditor } from "@/components/portal/sections/lab-onboarding";
import type { MyLab } from "@/lib/portal/types";

/** A member with owner/admin/PI rights on a lab may run its setup/edit flow. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/** Derive time-of-day greeting word from the hour (0–23). */
function timeOfDay(hour: number): "morning" | "afternoon" | "evening" {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

/** First word (first name) from a full display name. */
function firstName(name: string): string {
  return name.split(" ")[0] ?? name;
}

/** Small panel header with a "view all" affordance to the full section. */
function PanelHeader({ title, onView }: { title: string; onView: () => void }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="font-serif text-lg font-semibold text-[var(--text-primary)]">
        {title}
      </h2>
      <button
        type="button"
        onClick={onView}
        className="group inline-flex items-center gap-1 text-[13px] font-semibold text-primary hover:underline"
      >
        View all
        <ArrowRightIcon
          size={12}
          aria-hidden="true"
          className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
        />
      </button>
    </div>
  );
}

/** The Overview's right column, top: the user's top three daily papers + %. */
function TopPapersPanel() {
  const { goToSection } = usePortal();
  const { data, isLoading } = useDailyReport();
  const top = (data?.suggestions ?? []).slice(0, 3);

  return (
    <Card className="p-5">
      <PanelHeader title="Research Papers" onView={() => goToSection("papers")} />
      {isLoading ? (
        <p className="text-sm text-[var(--text-muted)]">
          Gathering today&apos;s papers…
        </p>
      ) : top.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <DocumentIcon size={16} />
          Your first paper matches will appear here after tonight&apos;s scan.
        </div>
      ) : (
        <ul className="space-y-3">
          {top.map((paper) => (
            <li
              key={paper.content_id}
              className="flex items-start justify-between gap-3"
            >
              <div className="flex min-w-0 items-start gap-2.5">
                {paper.rank ? (
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-[11px] font-semibold text-primary">
                    {paper.rank}
                  </span>
                ) : null}
                <span className="min-w-0 text-sm font-medium leading-snug text-[var(--text-primary)]">
                  {paper.headline || paper.title}
                </span>
              </div>
              <MatchBadge percent={paper.match_percent} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The Overview's right column, below papers: the soonest saved deadlines. */
function DeadlinesPanel() {
  const { goToSection } = usePortal();
  const { data, isLoading } = useDeadlines();
  const items = (data?.items ?? []).slice(0, 4);

  return (
    <Card className="p-5">
      <PanelHeader title="Deadlines" onView={() => goToSection("deadlines")} />
      {isLoading ? (
        <p className="text-sm text-[var(--text-muted)]">Loading your deadlines…</p>
      ) : items.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <CalendarIcon size={16} />
          Save a grant or conference to start tracking its deadline here.
        </div>
      ) : (
        <ul className="space-y-2.5">
          {items.map((item) => {
            const days = item.days_remaining;
            const label =
              days === null
                ? ""
                : days < 0
                  ? "Passed"
                  : days === 0
                    ? "Due today"
                    : `${days}d left`;
            return (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="min-w-0 truncate text-[var(--text-primary)]">
                  {item.title}
                </span>
                <span
                  className="shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold"
                  style={{
                    borderColor: item.within_week
                      ? "color-mix(in srgb, var(--accent) 45%, transparent)"
                      : "var(--border)",
                    color: item.within_week
                      ? "var(--accent)"
                      : "var(--text-secondary)",
                  }}
                >
                  {label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/**
 * The Overview section — the landing view of the portal dashboard. Two columns:
 * left holds Milo's weekly report, a 1×4 quick-nav grid, and next actions; right
 * holds the top research papers (with percent match) and the nearest deadlines.
 */
export function OverviewSection() {
  const {
    user,
    scopeLabel,
    goToSection,
    projects,
    labs,
    currentLab,
    labOnboardingEdit,
    setLabOnboardingEdit,
  } = usePortal();
  const profileQuery = useProfile();
  const watchQuery = useWatch();

  // When a lab is the active workspace, its overview replaces the personal one.
  if (currentLab) {
    if (labOnboardingEdit && canManageLab(currentLab)) {
      return (
        <LabEditor
          lab={currentLab}
          mode="edit"
          onDone={() => setLabOnboardingEdit(false)}
          onCancel={() => setLabOnboardingEdit(false)}
        />
      );
    }
    return <LabOverviewSection lab={currentLab} />;
  }

  const completeness = computeCompleteness(profileQuery.data);
  const watch = watchQuery.data;

  const now = new Date();
  const greeting = timeOfDay(now.getHours());
  const first = firstName(user.name || user.username);
  const dateLabel = now.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const watchTopicsCount = watch?.topics?.length ?? null;
  const cadenceLabel = watch
    ? watch.cadence === "daily"
      ? "Daily"
      : "Weekly"
    : null;

  return (
    <div>
      {/* Greeting */}
      <div className="mb-[22px]">
        <h1 className="m-0 mb-[6px] font-serif text-[31px] font-semibold leading-[1.12] tracking-[-0.015em] text-[var(--text-primary)]">
          Good {greeting}, {first}
        </h1>
        <p className="m-0 text-[14px] text-[var(--text-secondary)]">
          {dateLabel} · You&apos;re viewing {scopeLabel}
        </p>
      </div>

      {/* Two 50/50 columns: report + quick nav + next actions | papers + deadlines. */}
      <div className="grid grid-cols-1 items-start gap-[22px] lg:grid-cols-2">
        {/* Left column */}
        <div className="flex flex-col gap-[22px]">
          <MyloSummaryCard />

          {/* 1×4 quick-nav grid of smaller buttons. */}
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatCard
              icon={<FolderIcon size={16} />}
              label="Projects"
              value={projects.length}
              onClick={() => goToSection("projects" as SectionKey)}
            />
            <StatCard
              icon={<MembersIcon size={16} />}
              label="Labs"
              value={labs.length}
              onClick={() => goToSection("members" as SectionKey)}
            />
            <StatCard
              icon={<TargetIcon size={16} />}
              label="Profile"
              value={profileQuery.isLoading ? null : `${completeness.percent}%`}
              onClick={() => goToSection("profile" as SectionKey)}
            />
            <StatCard
              icon={<CalendarIcon size={16} />}
              label="Watching"
              value={watchQuery.isLoading ? null : watchTopicsCount}
              sub={
                watchQuery.isLoading || !cadenceLabel
                  ? undefined
                  : `${cadenceLabel} digest`
              }
              onClick={() => goToSection("profile" as SectionKey)}
            />
          </div>

          <NextActions />
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-[22px]">
          <TopPapersPanel />
          <DeadlinesPanel />
        </div>
      </div>
    </div>
  );
}
