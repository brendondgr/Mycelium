"use client";

import * as React from "react";

import { usePortal } from "@/components/portal/portal-context";
import { EditIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { LabEditorModal } from "@/components/portal/sections/lab-editor-modal";
import { MyloReportCard } from "@/components/portal/sections/mylo-report-card";
import { MyloFoundCard } from "@/components/portal/sections/mylo-found-card";
import {
  DeadlinesPanel,
  TopPapersPanel,
} from "@/components/portal/sections/overview-panels";
import { LabEditor } from "@/components/portal/sections/lab-onboarding";
import {
  useLabDailyBriefing,
  useLabProfile,
  useLabRecommendations,
  useLabSaves,
} from "@/lib/portal/hooks";
import type { MyLab } from "@/lib/portal/types";

/** Time-of-day greeting word from the hour (0–23). */
function timeOfDay(hour: number): "morning" | "afternoon" | "evening" {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

function firstName(name: string): string {
  return name.split(" ")[0] ?? name;
}

function canManage(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/**
 * The lab's front page — the landing view when a lab is the active workspace. It
 * mirrors the personal overview exactly: the greeting, then a two-column layout
 * with the lab's written "Mylo Report" (scrollable) on the left and, on the
 * right, what Mylo found for the lab (today / week / month / year), the top
 * matched papers, and the nearest saved deadlines. When the lab has no profile
 * yet, a manager sees inline onboarding here; a member sees an honest "not set
 * up yet" note.
 */
export function LabOverviewSection({ lab }: { lab: MyLab }) {
  const { user, scopeLabel } = usePortal();
  const profileQuery = useLabProfile(lab.slug);
  const recQuery = useLabRecommendations(lab.slug);
  const briefingQuery = useLabDailyBriefing(lab.slug);
  const savesQuery = useLabSaves(lab.slug);
  const [editing, setEditing] = React.useState(false);

  const profile = profileQuery.data;
  const manage = canManage(lab);

  const now = new Date();
  const greeting = timeOfDay(now.getHours());
  const first = firstName(user.name || user.username);
  const dateLabel = now.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const profileEmpty =
    !profileQuery.isLoading &&
    !!profile &&
    !profile.statement &&
    (profile.areas?.length ?? 0) === 0;

  // Onboarding gate: an unconfigured lab either onboards (manager) or explains
  // itself (member).
  if (profileEmpty) {
    if (manage) {
      return (
        <LabEditor lab={lab} onDone={() => profileQuery.refetch()} />
      );
    }
    return (
      <div>
        <Greeting
          greeting={greeting}
          first={first}
          dateLabel={dateLabel}
          scopeLabel={scopeLabel}
        />
        <Card className="p-6">
          <p className="text-[14px] text-[var(--text-secondary)]">
            This lab hasn&apos;t set up its research profile yet. Once a lab lead
            describes its purpose and focus, Mylo can start surfacing papers,
            grants, and conferences here.
          </p>
        </Card>
      </div>
    );
  }

  const rec = recQuery.data;

  return (
    <div className="flex h-full flex-col">
      <Greeting
        greeting={greeting}
        first={first}
        dateLabel={dateLabel}
        scopeLabel={scopeLabel}
        action={
          manage ? (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="inline-flex items-center gap-[7px] rounded-full border border-border bg-surface px-4 py-[9px] text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <EditIcon size={14} />
              Edit profile
            </button>
          ) : null
        }
      />

      {/* Report left; what Mylo found + papers + deadlines right. Each column is
          its own scroll region at `lg` — structurally identical to the personal
          overview so the two sides scroll independently. */}
      <div className="grid grid-cols-1 gap-[22px] lg:min-h-0 lg:flex-1 lg:grid-cols-[1.5fr_1fr]">
        {/* Left: the lab's written Mylo Report. */}
        <MyloReportCard
          data={briefingQuery.data}
          isLoading={briefingQuery.isLoading}
          title="Lab Mylo Report"
          scrollable
        />

        {/* Right: what Mylo found + top papers + nearest deadlines. */}
        <div className="flex flex-col gap-[22px] lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          <MyloFoundCard
            windowCounts={rec?.window_counts}
            isLoading={recQuery.isLoading}
          />

          <TopPapersPanel
            suggestions={rec?.papers ?? []}
            isLoading={recQuery.isLoading}
            recommendedFor={rec?.recommended_for}
          />
          <DeadlinesPanel
            items={savesQuery.data?.items ?? []}
            isLoading={savesQuery.isLoading}
          />
        </div>
      </div>

      {editing ? (
        <LabEditorModal lab={lab} onClose={() => setEditing(false)} />
      ) : null}
    </div>
  );
}

function Greeting({
  greeting,
  first,
  dateLabel,
  scopeLabel,
  action,
}: {
  greeting: string;
  first: string;
  dateLabel: string;
  scopeLabel: string;
  /** Trailing control (the manager-only "Edit profile" button). */
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-[22px] flex shrink-0 flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="m-0 mb-[6px] font-serif text-[31px] font-semibold leading-[1.12] tracking-[-0.015em] text-[var(--text-primary)]">
          Good {greeting}, {first}
        </h1>
        <p className="m-0 text-[14px] text-[var(--text-secondary)]">
          {dateLabel} · You&apos;re viewing {scopeLabel}
        </p>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
