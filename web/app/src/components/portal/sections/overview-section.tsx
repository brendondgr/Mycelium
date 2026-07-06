"use client";

import { usePortal, type SectionKey } from "@/components/portal/portal-context";
import { useProfile, useWatch } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";
import {
  FolderIcon,
  MembersIcon,
  ReportIcon,
  TargetIcon,
} from "@/components/portal/icons";

import { MyloSummaryCard } from "@/components/portal/sections/mylo-summary-card";
import { DailyDigestPanel } from "@/components/portal/sections/daily-digest-panel";
import { StatCard } from "@/components/portal/sections/stat-card";
import { NextActions } from "@/components/portal/sections/next-actions";
import { ProfileNudge } from "@/components/portal/sections/profile-nudge";
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
 * The Overview section — the landing view of the portal dashboard. Composes
 * the greeting, Mylo summary, stat grid, next-actions list, and profile nudge.
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
  // Opening "Edit setup" renders the editor directly here so the heavier lab
  // overview (member + project fetches) never mounts — the edit page loads fast.
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
  const hour = now.getHours();
  const greeting = timeOfDay(hour);
  const first = firstName(user.name || user.username);

  // Format: "Monday, June 29"
  const dateLabel = now.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  // Watch stats
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
        <h1 className="font-serif text-[31px] font-semibold leading-[1.12] tracking-[-0.015em] text-[var(--text-primary)] m-0 mb-[6px]">
          Good {greeting}, {first}
        </h1>
        <p className="m-0 text-[14px] text-[var(--text-secondary)]">
          {dateLabel} · You&apos;re viewing {scopeLabel}
        </p>
      </div>

      {/* Research radar (left) + daily report synopsis & notices (right) */}
      <div className="mb-[22px] grid gap-[22px] grid-cols-1 lg:grid-cols-[1.5fr_1fr] lg:items-stretch">
        <MyloSummaryCard />
        <DailyDigestPanel />
      </div>

      {/* Stat grid */}
      <div className="grid gap-[22px] [grid-template-columns:repeat(auto-fit,minmax(212px,1fr))] mb-[26px]">
        <StatCard
          icon={<FolderIcon size={16} />}
          label="Your projects"
          value={projects.length}
          onClick={() => goToSection("projects" as SectionKey)}
        />
        <StatCard
          icon={<MembersIcon size={16} />}
          label="Your labs"
          value={labs.length}
          onClick={() => goToSection("members" as SectionKey)}
        />
        <StatCard
          icon={<TargetIcon size={16} />}
          label="Profile"
          value={
            profileQuery.isLoading ? null : `${completeness.percent}%`
          }
          sub={
            profileQuery.isLoading
              ? undefined
              : `${completeness.doneCount}/${completeness.total} complete`
          }
          onClick={() => goToSection("profile" as SectionKey)}
        />
        <StatCard
          icon={<ReportIcon size={16} />}
          label="Watching"
          value={
            watchQuery.isLoading ? null : watchTopicsCount
          }
          sub={
            watchQuery.isLoading || !cadenceLabel
              ? undefined
              : `${cadenceLabel} digest`
          }
          onClick={() => goToSection("profile" as SectionKey)}
        />
      </div>

      {/* Next actions + profile nudge */}
      <div className="grid gap-[22px] grid-cols-1 lg:grid-cols-[1.4fr_1fr] items-start">
        <NextActions />
        <ProfileNudge />
      </div>
    </div>
  );
}
