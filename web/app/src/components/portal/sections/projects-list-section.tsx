"use client";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ChevronRightIcon,
  FolderIcon,
  PlusIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import {
  displayStatus,
  statusPillTone,
} from "@/components/portal/project-status";

/** Returns a relative time string for a given ISO date string. */
function relativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 14) return "1 week ago";
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 5) return `${diffWeeks} weeks ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths} month${diffMonths === 1 ? "" : "s"} ago`;
  const diffYears = Math.floor(diffDays / 365);
  return `${diffYears} year${diffYears === 1 ? "" : "s"} ago`;
}

export function ProjectsListSection() {
  const {
    projects,
    projectsLoading,
    projectsError,
    scopeLabel,
    openProject,
  } = usePortal();

  const newProjectAction = (
    <button
      type="button"
      disabled
      title="Project creation — coming soon"
      className="inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] opacity-50 cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <PlusIcon size={15} />
      New project
    </button>
  );

  return (
    <div>
      <SectionHeader
        title="Projects"
        subtitle={`Active research projects across ${scopeLabel}. Open one for its feed.`}
        action={newProjectAction}
      />

      {projectsLoading ? (
        <Card className="overflow-hidden">
          {/* Column header row */}
          <div className="flex items-center gap-[14px] border-b border-[var(--divider)] px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--text-muted)]">
            <span className="flex-1">Project</span>
            <span className="w-[120px]">Status</span>
            <span className="w-[150px]">Progress</span>
            <span className="w-24">Team</span>
            <span className="w-[18px]" />
          </div>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="animate-pulse border-b border-[var(--divider)] px-5 py-4"
            >
              <div className="h-14 rounded-xl bg-surface-alt" />
            </div>
          ))}
        </Card>
      ) : projectsError ? (
        <p className="text-sm text-[var(--text-muted)]">
          Couldn&apos;t load your projects.
        </p>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={<FolderIcon size={28} />}
          title="No projects yet"
          description={`Projects scoped to ${scopeLabel} will appear here. Project creation is coming soon.`}
        />
      ) : (
        <Card className="overflow-hidden">
          {/* Column header row */}
          <div className="flex items-center gap-[14px] border-b border-[var(--divider)] px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--text-muted)]">
            <span className="flex-1">Project</span>
            <span className="w-[120px]">Status</span>
            <span className="w-[150px]">Progress</span>
            <span className="w-24">Team</span>
            <span className="w-[18px]" />
          </div>

          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => openProject(p.id)}
              className="flex w-full items-center gap-[14px] border-b border-[var(--divider)] bg-transparent px-5 py-4 text-left font-[inherit] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring last:border-b-0"
            >
              {/* Name + updated */}
              <div className="min-w-0 flex-1">
                <p className="m-0 truncate text-sm font-medium text-[var(--text-primary)]">
                  {p.name}
                </p>
                <p className="m-0 text-[11.5px] text-[var(--text-muted)]">
                  Updated {relativeTime(p.updated_at)}
                </p>
              </div>

              {/* Status */}
              <span className="w-[120px]">
                <Pill tone={statusPillTone(p.status)}>
                  {displayStatus(p.status)}
                </Pill>
              </span>

              {/* Progress */}
              <div className="w-[150px]">
                {p.progress !== null ? (
                  <>
                    <ProgressBar value={p.progress} />
                    <span className="mt-1 block text-[11px] text-[var(--text-muted)]">
                      {p.progress}%
                    </span>
                  </>
                ) : (
                  <span className="text-[11px] text-[var(--text-muted)]">—</span>
                )}
              </div>

              {/* Team */}
              <span className="w-24 text-[12.5px] text-[var(--text-secondary)]">
                {p.member_count} member{p.member_count === 1 ? "" : "s"}
              </span>

              {/* Chevron */}
              <ChevronRightIcon
                size={18}
                className="shrink-0 text-[var(--text-muted)]"
              />
            </button>
          ))}
        </Card>
      )}
    </div>
  );
}
