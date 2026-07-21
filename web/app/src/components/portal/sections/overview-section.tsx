"use client";

import { usePortal } from "@/components/portal/portal-context";
import {
  useDailyBriefing,
  useDailyReport,
  useDeadlines,
  useWindowCounts,
} from "@/lib/portal/hooks";

import { MyloReportCard } from "@/components/portal/sections/mylo-report-card";
import { MyloFoundCard } from "@/components/portal/sections/mylo-found-card";
import {
  DeadlinesPanel,
  TopPapersPanel,
} from "@/components/portal/sections/overview-panels";
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

/**
 * The Overview section — the landing view of the portal dashboard. Two columns:
 * left holds Mylo's weekly report (scrollable, so a long write-up doesn't push
 * the page taller than the screen); right holds what Mylo found this year, the
 * top research papers (with percent match), and the nearest deadlines.
 */
export function OverviewSection() {
  const { user, scopeLabel, currentLab, labOnboardingEdit, setLabOnboardingEdit } =
    usePortal();
  const briefingQuery = useDailyBriefing();
  const windowCountsQuery = useWindowCounts();
  const dailyReportQuery = useDailyReport();
  const deadlinesQuery = useDeadlines();

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

  const now = new Date();
  const greeting = timeOfDay(now.getHours());
  const first = firstName(user.name || user.username);
  const dateLabel = now.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="flex h-full flex-col">
      {/* Greeting */}
      <div className="mb-[22px] shrink-0">
        <h1 className="m-0 mb-[6px] font-serif text-[31px] font-semibold leading-[1.12] tracking-[-0.015em] text-[var(--text-primary)]">
          Good {greeting}, {first}
        </h1>
        <p className="m-0 text-[14px] text-[var(--text-secondary)]">
          {dateLabel} · You&apos;re viewing {scopeLabel}
        </p>
      </div>

      {/* Report left; what Mylo found + papers + deadlines right. Each column is
          its own scroll region at `lg` so the two sides scroll independently. */}
      <div className="grid grid-cols-1 gap-[22px] lg:min-h-0 lg:flex-1 lg:grid-cols-[1.5fr_1fr]">
        {/* Left: the folded-in Mylo Report (was a standalone Daily page). */}
        <MyloReportCard
          data={briefingQuery.data}
          isLoading={briefingQuery.isLoading}
          scrollable
        />

        {/* Right: what Mylo found + top papers + nearest deadlines. */}
        <div className="flex flex-col gap-[22px] lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          <MyloFoundCard
            windowCounts={windowCountsQuery.data?.window_counts}
            isLoading={windowCountsQuery.isLoading}
          />

          <TopPapersPanel
            suggestions={dailyReportQuery.data?.suggestions ?? []}
            isLoading={dailyReportQuery.isLoading}
          />
          <DeadlinesPanel
            items={deadlinesQuery.data?.items ?? []}
            isLoading={deadlinesQuery.isLoading}
          />
        </div>
      </div>
    </div>
  );
}
