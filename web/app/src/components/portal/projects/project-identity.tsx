"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Pill } from "@/components/portal/primitives/pill";
import {
  EditIcon,
  MembersIcon,
  SporeNode,
} from "@/components/portal/icons";
import {
  displayStatus,
  statusPillTone,
} from "@/components/portal/project-status";
import { labLogoUrl } from "@/lib/portal/client";
import type { MyLab, Project, ProjectMember } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** A relative time string for an ISO date ("today", "3 days ago", "2 months ago"). */
export function relativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffDays = Math.floor(
    (now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24),
  );

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

/**
 * The faint root-network motif behind the project banner — the style guide's
 * "low-opacity connective tissue". Decorative only, and quiet enough that it
 * never competes with the title.
 */
function MyceliumTrace() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 420 160"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-y-0 right-0 hidden h-full w-[420px] text-primary opacity-[0.07] sm:block"
    >
      <g fill="none" stroke="currentColor" strokeWidth="1.2">
        <path d="M420 18 C 330 34, 300 74, 208 84 C 140 92, 96 68, 20 92" />
        <path d="M420 66 C 340 72, 296 108, 214 116 C 156 122, 110 112, 42 132" />
        <path d="M420 120 C 350 118, 318 82, 250 60 C 196 42, 150 40, 96 22" />
        <path d="M300 30 C 288 60, 268 82, 234 96" />
        <path d="M356 140 C 340 112, 314 96, 276 88" />
      </g>
      <g fill="currentColor">
        {[
          [208, 84],
          [214, 116],
          [250, 60],
          [96, 22],
          [42, 132],
          [276, 88],
        ].map(([cx, cy]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="3" />
        ))}
      </g>
    </svg>
  );
}

/**
 * The lab-or-personal badge — the cue that was missing entirely. A lab project
 * wears its lab's mark (its uploaded logo when the reader is a member of that
 * lab and it has one, else a spore glyph) and its name; a personal project wears
 * a quieter neutral badge. The two never rely on tone alone: each carries its
 * own icon and the words "Lab project" / "Personal project".
 */
function ScopeBadge({ project, lab }: { project: Project; lab: MyLab | null }) {
  const isLab = project.scope === "lab";
  const isDept = project.scope === "department";
  const logo = lab && lab.has_logo ? labLogoUrl(lab.slug, lab.logo_version) : null;

  if (!isLab && !isDept) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-alt px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)]">
        <Avatar initials="" seed={project.id} size={14} />
        Personal project
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-[color-mix(in_srgb,var(--primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] py-1 pl-1.5 pr-3 text-[11px] font-semibold text-primary">
      {logo ? (
        // A user-supplied logo served from our own API; a plain img is right here.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logo}
          alt=""
          className="h-[18px] w-[18px] rounded-full object-contain"
        />
      ) : (
        <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_22%,transparent)]">
          <SporeNode size={11} />
        </span>
      )}
      <span className="max-w-[26ch] truncate">{project.scope_name}</span>
      <span aria-hidden className="opacity-45">
        ·
      </span>
      {isDept ? "Department project" : "Lab project"}
    </span>
  );
}

/** Up to four member faces, then a "+N" counter. */
function MemberFaces({ members, total }: { members: ProjectMember[]; total: number }) {
  if (total === 0) {
    return (
      <span className="text-[12.5px] text-[var(--text-secondary)]">No members yet</span>
    );
  }
  const shown = members.slice(0, 4);
  return (
    <span className="flex items-center gap-2">
      <span className="flex -space-x-1.5">
        {shown.map((m) => (
          <span
            key={m.username}
            title={m.name}
            className="rounded-full ring-2 ring-[var(--surface)]"
          >
            <Avatar initials={m.initials} seed={m.username} size={22} />
          </span>
        ))}
      </span>
      <span className="text-[12.5px] text-[var(--text-secondary)]">
        {total} member{total === 1 ? "" : "s"}
      </span>
    </span>
  );
}

/**
 * The project banner: who owns it, what it is called, what it is about, and the
 * one action that changes any of that.
 *
 * This is the page's identity. Before it, a project read like any other listing —
 * a title, a description, and a disabled Edit button — with nothing to say whether
 * it belonged to a lab or to you. The banner carries a scope badge, an accent rail
 * whose colour follows that scope, and a root-network trace, so a project page is
 * recognisable as one at a glance.
 */
export function ProjectIdentity({
  project,
  lab,
  onEdit,
  onManageMembers,
}: {
  project: Project;
  /** The owning lab, when the reader is a member of it — for the logo mark. */
  lab: MyLab | null;
  onEdit: () => void;
  onManageMembers: () => void;
}) {
  const isLab = project.scope !== "user";

  return (
    <section
      className={cn(
        "relative mb-[22px] overflow-hidden rounded-2xl border border-border bg-surface px-5 py-[18px] shadow-[var(--shadow)] sm:px-6",
        "border-l-4",
        isLab ? "border-l-primary" : "border-l-brand-secondary",
      )}
    >
      <MyceliumTrace />

      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
            <ScopeBadge project={project} lab={lab} />
            {project.is_archived ? <Pill tone="neutral">Archived</Pill> : null}
            {project.is_over_cap ? <Pill tone="clay">Over plan limit</Pill> : null}
          </div>

          <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text-primary)]">
            {project.name}
          </h1>

          <p className="mt-2 max-w-[74ch] text-sm leading-[1.55] text-[var(--text-secondary)]">
            {project.description ?? (
              <span className="italic">
                No description yet — add one from Edit project.
              </span>
            )}
          </p>

          <div className="mt-3.5 flex flex-wrap items-center gap-x-3 gap-y-2">
            <Pill tone={statusPillTone(project.status)}>
              {displayStatus(project.status)}
            </Pill>
            {project.progress !== null ? (
              <span className="text-[12.5px] text-[var(--text-secondary)]">
                {project.progress}% complete
              </span>
            ) : null}
            <span aria-hidden className="text-[var(--text-muted)]">
              ·
            </span>
            <MemberFaces members={project.members} total={project.member_count} />
            <span aria-hidden className="text-[var(--text-muted)]">
              ·
            </span>
            <span className="text-[12.5px] text-[var(--text-secondary)]">
              updated {relativeTime(project.updated_at)}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onManageMembers}
            className="inline-flex items-center gap-[7px] rounded-full border border-border bg-surface px-[15px] py-[9px] text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <MembersIcon size={14} aria-hidden="true" />
            {project.can_manage_members ? "Members" : "Team"}
          </button>
          {project.can_edit ? (
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex items-center gap-[7px] rounded-full bg-primary px-[15px] py-[9px] text-[12.5px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <EditIcon size={14} aria-hidden="true" />
              Edit project
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
