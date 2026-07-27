"use client";

import {
  ChevronDownIcon,
  ChevronUpIcon,
  FolderIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { statusDotColor } from "@/components/portal/project-status";
import { cn } from "@/lib/utils";

/**
 * The expandable "Projects" sidebar entry: a parent row (opens the list) with a
 * count, an expand toggle, and — when open — an "All projects" link plus one row
 * per visible project, each a colored status dot and a click into its detail.
 */
export function ProjectsNav() {
  const {
    section,
    activeProjectId,
    projects,
    projectsLoading,
    projectsExpanded,
    toggleProjectsExpanded,
    openProjectsList,
    openProject,
  } = usePortal();

  const active = section === "projects";
  const allActive = active && activeProjectId == null;

  return (
    <div>
      <div className="relative flex items-center">
        <button
          type="button"
          onClick={openProjectsList}
          aria-current={active ? "page" : undefined}
          className={cn(
            "relative flex flex-1 items-center gap-3 rounded-[10px] py-2.5 pl-4 pr-10 text-left text-[13.5px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            active
              ? "font-semibold text-[var(--text-primary)]"
              : "font-medium text-[var(--text-secondary)]",
          )}
        >
          {active ? (
            <>
              <span
                aria-hidden
                className="absolute inset-0 rounded-[10px] bg-[color-mix(in_srgb,var(--primary)_13%,transparent)]"
              />
              <span
                aria-hidden
                className="absolute bottom-2 left-0 top-2 w-[3px] rounded-full bg-primary"
              />
            </>
          ) : null}
          <span className="relative shrink-0">
            <FolderIcon size={18} />
          </span>
          <span className="relative flex-1">Projects</span>
          <span className="relative rounded-full bg-surface-alt px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]">
            {projectsLoading ? "·" : projects.length}
          </span>
        </button>
        <button
          type="button"
          onClick={toggleProjectsExpanded}
          aria-label={projectsExpanded ? "Collapse projects" : "Expand projects"}
          aria-expanded={projectsExpanded}
          className="absolute right-1.5 flex h-6 w-6 items-center justify-center rounded-[7px] text-[var(--text-secondary)] transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {projectsExpanded ? (
            <ChevronUpIcon size={14} />
          ) : (
            <ChevronDownIcon size={14} />
          )}
        </button>
      </div>

      {projectsExpanded ? (
        <div className="ml-5 mt-0.5 flex flex-col gap-0.5 border-l border-[var(--divider)] pl-5">
          <button
            type="button"
            onClick={openProjectsList}
            className={cn(
              "relative rounded-lg px-2.5 py-1.5 text-left text-[12.5px] font-medium transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              allActive ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
            )}
          >
            {allActive ? (
              <span
                aria-hidden
                className="absolute inset-0 rounded-lg bg-[color-mix(in_srgb,var(--primary)_11%,transparent)]"
              />
            ) : null}
            <span className="relative">All projects</span>
          </button>

          {projects.map((project) => {
            const isActive = active && activeProjectId === project.id;
            return (
              <button
                key={project.id}
                type="button"
                onClick={() => openProject(project.id)}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[12.5px] font-medium transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive
                    ? "text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)]",
                )}
              >
                {isActive ? (
                  <span
                    aria-hidden
                    className="absolute inset-0 rounded-lg bg-[color-mix(in_srgb,var(--primary)_13%,transparent)]"
                  />
                ) : null}
                <span
                  className="relative h-[7px] w-[7px] shrink-0 rounded-full"
                  style={{ background: statusDotColor(project.status) }}
                />
                <span className="relative flex-1 truncate">{project.name}</span>
              </button>
            );
          })}

          {!projectsLoading && projects.length === 0 ? (
            <p className="px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)]">
              No projects yet.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
