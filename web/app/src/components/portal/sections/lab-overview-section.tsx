"use client";

import { roleLabel, usePortal, type SectionKey } from "@/components/portal/portal-context";
import {
  CalendarIcon,
  DocumentIcon,
  FolderIcon,
  MembersIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { StatCard } from "@/components/portal/sections/stat-card";
import { LabEditor } from "@/components/portal/sections/lab-onboarding";
import {
  useLabMembers,
  useLabProfile,
  useLabProjects,
  useLabRecommendations,
  useLabWatch,
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
 * The lab's front page — the landing view when a lab is the active workspace.
 * Modeled on the personal overview: a greeting, the date, and daily,
 * purpose-driven metrics (papers recommended, grants found, conferences
 * matching). When the lab has no profile yet, a manager sees inline onboarding
 * here instead; a member sees an honest "not set up yet" state.
 */
export function LabOverviewSection({ lab }: { lab: MyLab }) {
  const { user, goToSection, setLabOnboardingEdit } = usePortal();
  const profileQuery = useLabProfile(lab.slug);
  const watchQuery = useLabWatch(lab.slug);
  const membersQuery = useLabMembers(lab.slug);
  const projectsQuery = useLabProjects(lab.slug);
  const recQuery = useLabRecommendations(lab.slug);

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

  // Onboarding gate: an unconfigured lab either onboards (manager: the single-
  // page editor owns its own header) or explains itself (member).
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
  // Until Mylo has run for this lab there are no scores; say so rather than 0.
  const recSub = rec && !rec.generated_at ? "Awaiting first run" : undefined;

  return (
    <div>
      <Greeting greeting={greeting} first={first} dateLabel={dateLabel} lab={lab} />

      {/* Purpose-driven daily metrics — the lab's matched papers, grants, and
          conferences from its aggregate interests (its members + projects). */}
      <div className="mb-[26px] grid gap-[22px] [grid-template-columns:repeat(auto-fit,minmax(212px,1fr))]">
        <StatCard
          icon={<DocumentIcon size={16} />}
          label="Articles matched"
          value={rec?.counts.papers ?? null}
          sub={recSub}
        />
        <StatCard
          icon={<SparkleIcon size={16} />}
          label="Grants found"
          value={rec?.counts.grants ?? null}
          sub={recSub}
        />
        <StatCard
          icon={<CalendarIcon size={16} />}
          label="Conferences matching"
          value={rec?.counts.conferences ?? null}
          sub={recSub}
        />
        <StatCard
          icon={<SparkleIcon size={16} />}
          label="Fellowships eligible"
          value={rec?.counts.fellowships ?? null}
          sub="Members who opted in"
        />
        <StatCard
          icon={<MembersIcon size={16} />}
          label="Members"
          value={memberCount}
          onClick={() => goToSection("members" as SectionKey)}
        />
        <StatCard
          icon={<FolderIcon size={16} />}
          label="Projects"
          value={projectCount}
          onClick={() => goToSection("labs" as SectionKey)}
        />
      </div>

      {/* Fellowships members are eligible for — named only for members who opted
          into lab-visible eligibility; never anyone who is ineligible (D-11). */}
      {rec && rec.fellowships.length > 0 ? (
        <Card className="mb-[26px] p-5">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
            Fellowships your members are eligible for
          </h2>
          <ul className="space-y-3">
            {rec.fellowships.map((fellowship) => (
              <li
                key={fellowship.content_id}
                className="border-b border-[var(--divider)] pb-3 last:border-0 last:pb-0"
              >
                {fellowship.url ? (
                  <a
                    href={fellowship.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-semibold text-[var(--text-primary)] hover:text-primary"
                  >
                    {fellowship.title}
                  </a>
                ) : (
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {fellowship.title}
                  </p>
                )}
                {fellowship.deadline_date ? (
                  <p className="text-xs text-[var(--text-muted)]">
                    Deadline {fellowship.deadline_date}
                  </p>
                ) : null}
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {fellowship.eligible.map((member) => (
                    <span
                      key={member.username}
                      className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-alt px-2 py-0.5 text-xs text-[var(--text-secondary)]"
                    >
                      {member.name}{" "}
                      <span className="text-[var(--text-muted)]">
                        ({member.tier})
                      </span>
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {/* Lab purpose summary (left) + watch summary (right) */}
      <div className="grid gap-[22px] grid-cols-1 lg:grid-cols-[1.5fr_1fr] lg:items-start">
        <Card className="p-5">
          <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
            Lab purpose
          </h2>
          {profile?.statement ? (
            <p className="text-[14px] leading-relaxed text-[var(--text-secondary)]">
              {profile.statement}
            </p>
          ) : (
            <p className="text-[13.5px] text-[var(--text-muted)]">
              No statement yet.
            </p>
          )}
          {profile && profile.areas.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {profile.areas.map((area) => (
                <Pill key={area} tone="neutral">
                  {area}
                </Pill>
              ))}
            </div>
          ) : null}
          {manage ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => setLabOnboardingEdit(true)}
              >
                Edit setup
              </button>
              <button
                type="button"
                className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => goToSection("labs" as SectionKey)}
              >
                Manage lab
              </button>
            </div>
          ) : null}
        </Card>

        <Card className="p-5">
          <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
            What Mylo watches
          </h2>
          {watch && watch.topics.length > 0 ? (
            <>
              <div className="flex flex-wrap gap-1.5">
                {watch.topics.slice(0, 8).map((topic) => (
                  <Pill key={topic} tone="neutral">
                    {topic}
                  </Pill>
                ))}
              </div>
              <p className="mt-3 text-[12px] text-[var(--text-muted)]">
                {watch.categories.length} signal type
                {watch.categories.length === 1 ? "" : "s"} ·{" "}
                {watch.cadence === "daily" ? "Daily digest" : "Weekly digest"}
              </p>
            </>
          ) : (
            <p className="text-[13.5px] text-[var(--text-muted)]">
              Mylo isn&apos;t watching anything specific for this lab yet.
            </p>
          )}
        </Card>
      </div>
    </div>
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
    <div className="mb-[22px]">
      <h1 className="m-0 mb-[6px] font-serif text-[31px] font-semibold leading-[1.12] tracking-[-0.015em] text-[var(--text-primary)]">
        Good {greeting}, {first}
      </h1>
      <p className="m-0 text-[14px] text-[var(--text-secondary)]">
        {dateLabel} · You&apos;re viewing{" "}
        <span className="font-medium text-[var(--text-primary)]">{lab.name}</span>{" "}
        · {roleLabel(lab)}
      </p>
    </div>
  );
}
