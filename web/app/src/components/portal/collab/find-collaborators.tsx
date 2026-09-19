"use client";

import * as React from "react";

import {
  openCollaboratorSearch,
  sentence,
  type CollabSearchRequest,
} from "@/components/portal/collab/search-panel";
import { MembersIcon } from "@/components/portal/icons";
import { useSearchAvailability } from "@/lib/portal/collab/hooks";
import type { Project } from "@/lib/portal/types";

/**
 * The one button every entry point shares (collaboration-network plan CN-06).
 *
 * It renders only when a search would actually run — the flag is on, the
 * reader's email is verified, and their plan includes it — so no surface
 * offers something that would only be refused. A reader on the free plan gets
 * `upgradeNote` in its place when the surface asks for one.
 */
export function FindCollaboratorsButton({
  request,
  label = "Find collaborators",
  upgradeNote = false,
  className,
}: {
  request: CollabSearchRequest;
  label?: string;
  upgradeNote?: boolean;
  className?: string;
}) {
  const availability = useSearchAvailability();
  const data = availability.data;
  if (!data) return null;
  if (!data.available) {
    return upgradeNote && data.code === "paid_plan" ? (
      <span
        className={`text-[12px] text-[var(--text-muted)] ${className ?? ""}`}
      >
        Finding collaborators for a gap is part of a paid plan.
      </span>
    ) : null;
  }
  return (
    <button
      type="button"
      onClick={() => openCollaboratorSearch(request)}
      className={`inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className ?? ""}`}
    >
      <MembersIcon size={13} />
      {label}
    </button>
  );
}

/**
 * The project page's Collaborators tab: the project's own stated methods,
 * data and problem, searched against people outside its lab.
 */
export function ProjectCollaboratorsCard({ project }: { project: Project }) {
  const availability = useSearchAvailability();
  const data = availability.data;
  return (
    <div className="rounded-2xl border border-border bg-surface px-5 py-4">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Find collaborators for this project
      </p>
      <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
        Mylo reads the project&apos;s stated methods, data and problem, and
        looks for people outside your lab who are open to collaboration: some
        who bring what the project lacks, some who work on the same thing. Only
        people who chose to be findable, by you, are ever shown.
      </p>
      <div className="mt-3">
        {data && !data.available ? (
          <p className="text-[13px] text-[var(--text-muted)]">
            {data.code === "paid_plan"
              ? "Finding collaborators is part of a paid plan."
              : sentence(data.reason)}
          </p>
        ) : (
          <FindCollaboratorsButton
            request={{
              entry: { entry: "project", project_id: String(project.id) },
              title: project.name,
            }}
          />
        )}
      </div>
    </div>
  );
}
