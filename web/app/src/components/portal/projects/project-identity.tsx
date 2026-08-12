"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import { EditIcon, FolderIcon, SporeNode } from "@/components/portal/icons";
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
 * The lab-or-personal cue that was missing entirely. A lab project wears its
 * lab's mark — the uploaded logo when the reader belongs to that lab, else a
 * spore glyph — and its name; a personal project wears a quieter neutral badge.
 * Neither leans on colour alone: each carries its own icon and says in words
 * which kind of project this is.
 */
function ScopeBadge({ project, lab }: { project: Project; lab: MyLab | null }) {
  const isOrg = project.scope !== "user";
  const logo = lab?.has_logo ? labLogoUrl(lab.slug, lab.logo_version) : null;

  if (!isOrg) {
    return (
      <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface-alt px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)]">
        <FolderIcon size={12} aria-hidden="true" />
        Personal project
      </span>
    );
  }

  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-[color-mix(in_srgb,var(--primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] py-1 pl-1.5 pr-2.5 text-[11px] font-semibold text-primary">
      {logo ? (
        // A user-supplied logo served from our own API; a plain img is right here.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logo}
          alt=""
          className="h-[18px] w-[18px] shrink-0 rounded-full object-contain"
        />
      ) : (
        <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_22%,transparent)]">
          <SporeNode size={11} />
        </span>
      )}
      <span className="truncate">{project.scope_name}</span>
    </span>
  );
}

/** One label/value line in the identity card's detail list. */
function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-3">
      <dt className="w-[62px] shrink-0 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
        {label}
      </dt>
      <dd className="m-0 min-w-0 flex-1 text-[12.5px] text-[var(--text-secondary)]">
        {children}
      </dd>
    </div>
  );
}

/** Up to four member faces, then a "+N" counter. */
function MemberFaces({
  members,
  total,
}: {
  members: ProjectMember[];
  total: number;
}) {
  if (total === 0) {
    return <span className="text-[var(--text-muted)]">Nobody yet</span>;
  }
  const shown = members.slice(0, 4);
  return (
    <span className="flex flex-wrap items-center gap-2">
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
      <span>
        {total} member{total === 1 ? "" : "s"}
      </span>
    </span>
  );
}

/**
 * The project's identity card — the only thing in the overview's left column.
 *
 * It used to be a full-width banner that crammed the scope badge, status,
 * member faces, timestamp and two buttons onto one wrapping line, over a
 * stretched decorative graphic that read as a rendering glitch. This is the
 * opposite: a single column, a real label/value list that cannot collapse into
 * an unreadable row however narrow it gets, and one action.
 */
export function ProjectIdentity({
  project,
  lab,
  onEdit,
}: {
  project: Project;
  /** The owning lab, when the reader belongs to it — for the logo mark. */
  lab: MyLab | null;
  onEdit: () => void;
}) {
  const isOrg = project.scope !== "user";

  return (
    <Card
      className={cn(
        "border-l-4 p-5",
        isOrg ? "border-l-primary" : "border-l-brand-secondary",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <ScopeBadge project={project} lab={lab} />
        {project.is_archived ? <Pill tone="neutral">Archived</Pill> : null}
        {project.is_over_cap ? <Pill tone="clay">Over plan limit</Pill> : null}
      </div>

      <h1 className="mt-3 font-serif text-[23px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text-primary)]">
        {project.name}
      </h1>

      <p className="mt-2 text-[13px] leading-[1.55] text-[var(--text-secondary)]">
        {project.description ?? (
          <span className="italic text-[var(--text-muted)]">
            No description yet.
          </span>
        )}
      </p>

      <dl className="mt-4 space-y-3 border-t border-[var(--divider)] pt-4">
        <DetailRow label="Status">
          <Pill tone={statusPillTone(project.status)}>
            {displayStatus(project.status)}
          </Pill>
        </DetailRow>

        {project.progress !== null ? (
          <DetailRow label="Progress">
            <span className="block">{project.progress}%</span>
            <ProgressBar value={project.progress} className="mt-1.5" />
          </DetailRow>
        ) : null}

        <DetailRow label="Team">
          <MemberFaces members={project.members} total={project.member_count} />
        </DetailRow>

        <DetailRow label="Updated">{relativeTime(project.updated_at)}</DetailRow>
      </dl>

      {project.can_edit ? (
        <button
          type="button"
          onClick={onEdit}
          className="mt-4 inline-flex w-full items-center justify-center gap-[7px] rounded-full bg-primary px-[15px] py-[9px] text-[12.5px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <EditIcon size={14} aria-hidden="true" />
          Edit project
        </button>
      ) : null}
    </Card>
  );
}
