"use client";

import { roleLabel, usePortal, type SectionKey } from "@/components/portal/portal-context";
import { FolderIcon, MembersIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { MyloReportCard } from "@/components/portal/sections/mylo-report-card";
import { MyloFoundCard } from "@/components/portal/sections/mylo-found-card";
import { StatCard } from "@/components/portal/sections/stat-card";
import { LabEditor } from "@/components/portal/sections/lab-onboarding";
import {
  useLabDailyBriefing,
  useLabMembers,
  useLabProfile,
  useLabProjects,
  useLabRecommendations,
  useLabWatch,
} from "@/lib/portal/hooks";
import type { LabFellowship, MyLab } from "@/lib/portal/types";

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
 * The lab's front page — the landing view when a lab is the active workspace. Left
 * column is the lab's written "Mylo Report"; the right column is a tight column of
 * lab statistics: purpose + what Mylo watches, a recency matrix of what Mylo found
 * (today / this week / month / year, per area), and members & projects. When the
 * lab has no profile yet, a manager sees inline onboarding here; a member sees an
 * honest "not set up yet" note.
 */
export function LabOverviewSection({ lab }: { lab: MyLab }) {
  const { user, goToSection } = usePortal();
  const profileQuery = useLabProfile(lab.slug);
  const watchQuery = useLabWatch(lab.slug);
  const membersQuery = useLabMembers(lab.slug);
  const projectsQuery = useLabProjects(lab.slug);
  const recQuery = useLabRecommendations(lab.slug);
  const briefingQuery = useLabDailyBriefing(lab.slug);

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
      return <LabEditor lab={lab} mode="create" onDone={() => profileQuery.refetch()} />;
    }
    return (
      <div>
        <Greeting greeting={greeting} first={first} dateLabel={dateLabel} lab={lab} />
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

  const memberCount = membersQuery.data?.length ?? null;
  const projectCount = projectsQuery.data?.length ?? null;
  const watch = watchQuery.data;
  const rec = recQuery.data;

  return (
    <div>
      <Greeting greeting={greeting} first={first} dateLabel={dateLabel} lab={lab} />

      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] lg:items-start">
        {/* Left: the lab's written Mylo Report. */}
        <MyloReportCard
          data={briefingQuery.data}
          isLoading={briefingQuery.isLoading}
          title="Lab Mylo Report"
        />

        {/* Right: a tight column of lab statistics. */}
        <div className="flex flex-col gap-4">
          <PurposeWatchCard
            statement={profile?.statement ?? ""}
            areas={profile?.areas ?? []}
            watchTopics={watch?.topics ?? []}
            manage={manage}
            onEdit={() => goToSection("profile" as SectionKey)}
          />

          <MyloFoundCard
            windowCounts={rec?.window_counts}
            isLoading={recQuery.isLoading}
          />

          <div className="grid grid-cols-2 gap-3">
            <StatCard
              icon={<MembersIcon size={15} />}
              label="Members"
              value={memberCount}
              onClick={() => goToSection("members" as SectionKey)}
            />
            <StatCard
              icon={<FolderIcon size={15} />}
              label="Projects"
              value={projectCount}
              onClick={() => goToSection("projects" as SectionKey)}
            />
          </div>

          {rec && rec.fellowships.length > 0 ? (
            <FellowshipsCard fellowships={rec.fellowships} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

/* -- Purpose + watch (compact) ---------------------------------------------- */

function PurposeWatchCard({
  statement,
  areas,
  watchTopics,
  manage,
  onEdit,
}: {
  statement: string;
  areas: string[];
  watchTopics: string[];
  manage: boolean;
  onEdit: () => void;
}) {
  return (
    <Card className="p-5">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
          Lab purpose
        </h2>
        {manage ? (
          <button
            type="button"
            onClick={onEdit}
            className="text-[12px] font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Edit
          </button>
        ) : null}
      </div>
      {statement ? (
        <p className="text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
          {statement}
        </p>
      ) : (
        <p className="text-[13px] text-[var(--text-muted)]">No statement yet.</p>
      )}
      {areas.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {areas.slice(0, 8).map((area) => (
            <Pill key={area} tone="neutral">
              {area}
            </Pill>
          ))}
        </div>
      ) : null}
      {watchTopics.length > 0 ? (
        <p className="mt-3 border-t border-[var(--divider)] pt-2.5 text-[12px] text-[var(--text-muted)]">
          <span className="font-medium text-[var(--text-secondary)]">
            Mylo watches:
          </span>{" "}
          {watchTopics.slice(0, 6).join(" · ")}
        </p>
      ) : null}
    </Card>
  );
}

/* -- Fellowships members are eligible for (compact) ------------------------- */

function FellowshipsCard({
  fellowships,
}: {
  fellowships: LabFellowship[];
}) {
  return (
    <Card className="p-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
        Fellowships your members are eligible for
      </h2>
      <ul className="space-y-2.5">
        {fellowships.slice(0, 4).map((fellowship) => (
          <li
            key={fellowship.content_id}
            className="border-b border-[var(--divider)] pb-2.5 last:border-0 last:pb-0"
          >
            {fellowship.url ? (
              <a
                href={fellowship.url}
                target="_blank"
                rel="noreferrer"
                className="text-[13.5px] font-semibold text-[var(--text-primary)] hover:text-primary"
              >
                {fellowship.title}
              </a>
            ) : (
              <p className="text-[13.5px] font-semibold text-[var(--text-primary)]">
                {fellowship.title}
              </p>
            )}
            <div className="mt-1 flex flex-wrap gap-1.5">
              {fellowship.eligible.slice(0, 5).map((member) => (
                <span
                  key={member.username}
                  className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-alt px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
                >
                  {member.name}{" "}
                  <span className="text-[var(--text-muted)]">({member.tier})</span>
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Greeting({
  greeting,
  first,
  dateLabel,
  lab,
}: {
  greeting: string;
  first: string;
  dateLabel: string;
  lab: MyLab;
}) {
  return (
    <div className="mb-[18px]">
      <h1 className="m-0 mb-[6px] font-serif text-[28px] font-semibold leading-[1.12] tracking-[-0.015em] text-[var(--text-primary)]">
        Good {greeting}, {first}
      </h1>
      <p className="m-0 text-[13.5px] text-[var(--text-secondary)]">
        {dateLabel} · You&apos;re viewing{" "}
        <span className="font-medium text-[var(--text-primary)]">{lab.name}</span>{" "}
        · {roleLabel(lab)}
      </p>
    </div>
  );
}
