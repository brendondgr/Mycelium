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
import { StatCard } from "@/components/portal/sections/stat-card";
import { NextActions } from "@/components/portal/sections/next-actions";
import { ProfileNudge } from "@/components/portal/sections/profile-nudge";

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
  const { user, scopeLabel, goToSection, projects, labs } = usePortal();
  const profileQuery = useProfile();
  const watchQuery = useWatch();

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
    ? watch.cadence === "realtime"
      ? "Real-time"
      : watch.cadence === "daily"
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

      {/* Mylo summary */}
      <div className="mb-[22px]">
        <MyloSummaryCard />
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
          onClick={() => goToSection("goals" as SectionKey)}
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
          onClick={() => goToSection("goals" as SectionKey)}
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
