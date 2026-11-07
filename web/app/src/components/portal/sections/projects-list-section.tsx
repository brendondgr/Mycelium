"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import { FindCollaboratorsButton } from "@/components/portal/collab/find-collaborators";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  AlertTriangleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  FolderIcon,
  PlusIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { CreateProjectWizard } from "@/components/portal/projects/create-project-wizard";
import {
  displayStatus,
  statusPillTone,
} from "@/components/portal/project-status";
import { useArchiveProject, useUnarchiveProject } from "@/lib/portal/hooks";
import { ProjectCapReachedError } from "@/lib/portal/mutations";
import type { Project } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

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

  const [showWizard, setShowWizard] = React.useState(false);
  const [showArchived, setShowArchived] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const active = React.useMemo(
    () => projects.filter((p) => !p.is_archived),
    [projects],
  );
  const archived = React.useMemo(
    () => projects.filter((p) => p.is_archived),
    [projects],
  );
  const anyOverCap = active.some((p) => p.is_over_cap);

  const newProjectAction = (
    <div className="flex flex-wrap items-center gap-2">
      <FindCollaboratorsButton
        className="py-[8px]"
        request={{
          entry: { entry: "manual", text: "" },
          title: "Describe what you need",
        }}
      />
      <button
        type="button"
        onClick={() => setShowWizard(true)}
        className="inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <PlusIcon size={15} />
        New project
      </button>
    </div>
  );

  return (
    <div>
      <SectionHeader
        eyebrow="Workspace"
        title="Projects"
        subtitle={`Active research projects across ${scopeLabel}. Open one for its feed.`}
        action={newProjectAction}
      />

      {anyOverCap ? (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-dashed border-clay bg-clay-soft px-4 py-3 text-[12.5px] leading-relaxed text-clay">
          <AlertTriangleIcon size={16} className="mt-[1px] shrink-0" />
          <span>
            Some projects are over this instance&apos;s project limit and have
            paused getting new recommendations. Archive one to resume, or ask
            an administrator to raise the limit.
          </span>
        </div>
      ) : null}

      {actionError ? (
        <div className="mb-4 flex items-start justify-between gap-3 rounded-xl border border-dashed border-clay bg-clay-soft px-4 py-3 text-[12.5px] leading-relaxed text-clay">
          <span>{actionError}</span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="shrink-0 font-semibold underline"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {projectsLoading ? (
        <Card className="overflow-hidden">
          {/* Column header row */}
          <div className="flex items-center gap-[14px] border-b border-[var(--divider)] px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--text-secondary)]">
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
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load your projects.
        </p>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={<FolderIcon size={28} />}
          title="No projects yet"
          description={`Start a project scoped to ${scopeLabel} — give it a focus and Mylo will start finding matches for it.`}
          action={
            <button
              type="button"
              onClick={() => setShowWizard(true)}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
            >
              New project
            </button>
          }
        />
      ) : (
        <div className="space-y-5">
          {active.length === 0 ? (
            <EmptyState
              icon={<FolderIcon size={28} />}
              title="No active projects"
              description="Every project here is archived. Start a new one, or unarchive one below."
            />
          ) : (
            <Card className="overflow-hidden">
              {/* Column header row */}
              <div className="flex items-center gap-[14px] border-b border-[var(--divider)] px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--text-secondary)]">
                <span className="flex-1">Project</span>
                <span className="w-[120px]">Status</span>
                <span className="w-[150px]">Progress</span>
                <span className="w-24">Team</span>
                <span className="w-[92px]" />
              </div>

              {active.map((p) => (
                <ProjectRow
                  key={p.id}
                  project={p}
                  onOpen={() => openProject(p.id)}
                  onError={setActionError}
                />
              ))}
            </Card>
          )}

          {archived.length > 0 ? (
            <div>
              <button
                type="button"
                onClick={() => setShowArchived((v) => !v)}
                aria-expanded={showArchived}
                className="flex items-center gap-1.5 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                <ChevronDownIcon
                  size={14}
                  className={cn(
                    "transition-transform duration-200 motion-reduce:transition-none",
                    showArchived && "rotate-180",
                  )}
                />
                Archived ({archived.length})
              </button>

              {showArchived ? (
                <Card className="mt-2.5 overflow-hidden opacity-80">
                  {archived.map((p) => (
                    <ProjectRow
                      key={p.id}
                      project={p}
                      onOpen={() => openProject(p.id)}
                      onError={setActionError}
                      muted
                    />
                  ))}
                </Card>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      {showWizard ? (
        <CreateProjectWizard onClose={() => setShowWizard(false)} />
      ) : null}
    </div>
  );
}

/** One project row: name/status/progress/team, plus an Archive/Unarchive
 * action. The name area is the primary click target (opens the project); the
 * archive control is a separate, sibling button so it never nests inside it. */
function ProjectRow({
  project,
  onOpen,
  onError,
  muted,
}: {
  project: Project;
  onOpen: () => void;
  onError: (message: string) => void;
  muted?: boolean;
}) {
  const archive = useArchiveProject();
  const unarchive = useUnarchiveProject();
  const pending = archive.isPending || unarchive.isPending;

  const handleToggleArchive = () => {
    if (project.is_archived) {
      unarchive.mutate(project.id, {
        onError: (err) => {
          onError(
            err instanceof ProjectCapReachedError
              ? `Restoring "${project.name}" would exceed the limit of ${err.cap} active projects — archive another first.`
              : (err as Error).message,
          );
        },
      });
    } else {
      archive.mutate(project.id, {
        onError: (err) => onError((err as Error).message),
      });
    }
  };

  return (
    <div
      className={cn(
        "flex items-center gap-[14px] border-b border-[var(--divider)] px-5 py-4 last:border-b-0",
        !muted && "hover:bg-surface-alt",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 items-center gap-[14px] bg-transparent text-left font-[inherit] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {/* Name + updated */}
        <div className="min-w-0 flex-1">
          <p className="m-0 flex items-center gap-1.5 truncate text-sm font-medium text-[var(--text-primary)]">
            {project.name}
            {project.is_over_cap ? (
              <Pill tone="clay" className="shrink-0">
                Over limit
              </Pill>
            ) : null}
          </p>
          <p className="m-0 text-[11.5px] text-[var(--text-secondary)]">
            Updated {relativeTime(project.updated_at)}
          </p>
        </div>

        {/* Status */}
        <span className="w-[120px]">
          <Pill tone={statusPillTone(project.status)}>
            {displayStatus(project.status)}
          </Pill>
        </span>

        {/* Progress */}
        <div className="w-[150px]">
          {project.progress !== null ? (
            <>
              <ProgressBar value={project.progress} />
              <span className="mt-1 block text-[11px] text-[var(--text-secondary)]">
                {project.progress}%
              </span>
            </>
          ) : (
            <span className="text-[11px] text-[var(--text-secondary)]">—</span>
          )}
        </div>

        {/* Team */}
        <span className="w-24 text-[12.5px] text-[var(--text-secondary)]">
          {project.member_count} member{project.member_count === 1 ? "" : "s"}
        </span>

        {/* Chevron */}
        <ChevronRightIcon
          size={18}
          className="shrink-0 text-[var(--text-secondary)]"
        />
      </button>

      <button
        type="button"
        onClick={handleToggleArchive}
        disabled={pending}
        className="shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      >
        {project.is_archived
          ? unarchive.isPending
            ? "Restoring…"
            : "Unarchive"
          : archive.isPending
            ? "Archiving…"
            : "Archive"}
      </button>
    </div>
  );
}
