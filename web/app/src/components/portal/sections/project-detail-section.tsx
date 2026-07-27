"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import {
  BankIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  CloseIcon,
  ConferenceIcon,
  DocumentIcon,
  EditIcon,
  LinkIcon,
  ListIcon,
  PlusIcon,
  SparkleIcon,
  SporeNode,
  TargetIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import {
  displayStatus,
  statusPillTone,
} from "@/components/portal/project-status";
import { ConferenceCard } from "@/components/portal/sections/conferences-section";
import { FellowshipRow } from "@/components/portal/sections/fellowships-section";
import { GrantRow } from "@/components/portal/sections/opportunities-section";
import { SuggestionCard } from "@/components/portal/sections/suggestion-card";
import {
  useAddToCollection,
  useArchiveProject,
  useCreateCollection,
  useIngestProjectLink,
  useProjectCollection,
  useProjectCollections,
  useProjectDigest,
  useProjectFeed,
  useProjectRecommendations,
  useRemoveFromCollection,
  useShareToProject,
  useUnarchiveProject,
  useUpdateCollection,
  useUpdateProjectCategories,
} from "@/lib/portal/hooks";
import {
  markProjectItemSeen,
  ProjectCapReachedError,
  recordProjectEvent,
} from "@/lib/portal/mutations";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type {
  BriefingCategory,
  CollectionBrief,
  ConferenceOpportunity,
  FellowshipOpportunity,
  GrantOpportunity,
  InterestedMember,
  MyLab,
  Project,
  ProjectFeedItem,
  ProjectMember,
  ProjectRecommendations,
  Suggestion,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** A member with owner/admin/PI rights may edit a lab-scoped project — mirrors
 * the backend's edit-permission check (owner/admin/PI, same as `canManageLab`
 * elsewhere). A personal project's only ever visible to its own owner. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/** Shared input style for the small inline forms on this page. */
const INPUT =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** A compact, area-labelled recommendation row for the sidebar. */
type MiniRec = { key: string; area: string; title: string; match: number | null; url: string };

/** Top few recommendations across areas for the sidebar "Recommended by Mylo" card. */
function topRecommendations(rec: ProjectRecommendations): MiniRec[] {
  const out: MiniRec[] = [];
  for (const p of rec.papers.slice(0, 3)) {
    out.push({ key: `p-${p.content_id}`, area: "Paper", title: p.title, match: p.match_percent, url: p.url });
  }
  for (const g of rec.grants.slice(0, 3)) {
    out.push({ key: `g-${g.content_id}`, area: "Grant", title: g.title, match: g.match_percent, url: g.url });
  }
  for (const c of rec.conferences.slice(0, 2)) {
    out.push({ key: `c-${c.content_id}`, area: "Conference", title: c.title, match: c.match_percent, url: c.url });
  }
  return out;
}

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

export function ProjectDetailSection() {
  const { projects, activeProjectId, openProjectsList, currentLab } = usePortal();

  const project = projects.find((p) => p.id === activeProjectId);
  // Hooks must run every render (before the early return), so each takes the id
  // optionally and stays disabled until a project is selected.
  const recQuery = useProjectRecommendations(project?.id);
  const feedQuery = useProjectFeed(project?.id);
  const digestQuery = useProjectDigest(project?.id);

  const backButton = (
    <button
      type="button"
      onClick={openProjectsList}
      className="mb-[14px] inline-flex items-center gap-[6px] rounded-full border-none bg-transparent px-[10px] py-[5px] text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ChevronLeftIcon size={15} />
      All projects
    </button>
  );

  if (!project) {
    return (
      <div>
        {backButton}
        <p className="text-sm text-[var(--text-secondary)]">Loading project…</p>
      </div>
    );
  }

  const goals = project.goals as Record<string, unknown>;
  const description =
    (typeof goals.description === "string" && goals.description) ||
    (typeof goals.goal === "string" && goals.goal) ||
    null;

  const goalLabel =
    (typeof goals.goal === "string" && goals.goal) || null;

  const rec = recQuery.data;
  const recPapers = rec?.papers ?? [];
  const recTotal = rec
    ? rec.counts.papers + rec.counts.grants + rec.counts.conferences
    : 0;
  const miniRecs = rec ? topRecommendations(rec) : [];
  const hasFocus = project.focus.areas.length > 0;
  const feedItems = feedQuery.data?.items ?? [];
  // Sharing/ingesting is backend-gated on participation (a non-member 403s);
  // the project's own membership flag lets the UI hide those affordances
  // upfront instead of reimplementing the gate client-side. A personal project
  // (scope "user") is only ever visible to its owner and carries no member row,
  // so its owner collaborates too — matching the backend participant gate.
  const canCollaborate = project.is_member || project.scope === "user";
  // Editing (focus/watch categories/archive) is narrower than collaborating:
  // the backend allows only the personal owner, or a lab's owner/admin/PI. A
  // lab project is normally only opened while that lab is the active
  // workspace, so its manager rights come from the current lab scope.
  const canEditProject =
    project.scope === "user" ||
    (project.scope === "lab" && currentLab !== null && canManageLab(currentLab));

  return (
    <div>
      {backButton}

      {/* Project header */}
      <div className="mb-[6px] flex flex-wrap items-start justify-between gap-[18px]">
        <div>
          <h1 className="mb-[7px] font-serif text-[27px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text-primary)]">
            {project.name}
          </h1>
          <div className="flex flex-wrap items-center gap-3">
            <Pill tone={statusPillTone(project.status)}>
              {displayStatus(project.status)}
            </Pill>
            <span className="text-[12.5px] text-[var(--text-secondary)]">
              updated {relativeTime(project.updated_at)}
            </span>
            {project.progress !== null && (
              <>
                <span className="text-[12.5px] text-[var(--text-secondary)]">·</span>
                <span className="text-[12.5px] text-[var(--text-secondary)]">
                  {project.progress}% complete
                </span>
              </>
            )}
          </div>
        </div>

        <button
          type="button"
          disabled
          title="Editing — coming soon"
          className="inline-flex shrink-0 items-center gap-[7px] rounded-full border border-border bg-surface px-[15px] py-[9px] text-[12.5px] font-semibold text-[var(--text-primary)] opacity-50 cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <EditIcon size={14} />
          Edit project
        </button>
      </div>

      {/* Description */}
      <p className="mb-[22px] max-w-[74ch] text-sm leading-[1.55] text-[var(--text-secondary)]">
        {description ?? (
          <span className="text-[var(--text-secondary)]">No description yet.</span>
        )}
      </p>

      {/* Responsive two-column grid */}
      <div className="grid items-start gap-[22px] lg:grid-cols-[1.55fr_1fr]">
        {/* LEFT column */}
        <div className="flex flex-col gap-[22px]">
          {/* Project feed */}
          <Card className="overflow-hidden">
            <div className="border-b border-[var(--divider)] px-5 pb-[14px] pt-[18px]">
              <h2 className="mb-[3px] text-base font-semibold text-[var(--text-primary)]">
                Project feed
              </h2>
              <p className="mb-[14px] text-[12.5px] text-[var(--text-secondary)]">
                Papers the team has shared, plus articles you paste in directly.
              </p>

              <IngestLinkForm projectId={project.id} canIngest={canCollaborate} />
            </div>

            {/* The team's shared feed — the primary content of this card. */}
            {feedQuery.isLoading ? (
              <div className="py-8 text-center">
                <p className="text-sm text-[var(--text-secondary)]">
                  Loading the shared feed…
                </p>
              </div>
            ) : feedQuery.isError ? (
              <div className="py-8 text-center">
                <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
                  Couldn&apos;t load the shared feed.
                </p>
              </div>
            ) : feedItems.length > 0 ? (
              <ul className="divide-y divide-[var(--divider)]">
                {feedItems.map((item) => (
                  <FeedItemRow
                    key={item.share_id}
                    item={item}
                    projectId={project.id}
                    canCollaborate={canCollaborate}
                  />
                ))}
              </ul>
            ) : (
              <div className="py-8 text-center">
                <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
                  No shared papers yet — paste a link above or share one of
                  Mylo&apos;s picks below.
                </p>
              </div>
            )}

            {/* Mylo's recommended papers for this project's focus, ready to push into the feed. */}
            <div className="border-t border-[var(--divider)] px-5 pb-[8px] pt-[16px]">
              <h3 className="mb-[3px] text-[13px] font-semibold text-[var(--text-primary)]">
                Recommended for this project
              </h3>
              <p className="text-[11.5px] text-[var(--text-secondary)]">
                Mylo&apos;s picks for this project&apos;s focus.
              </p>
            </div>
            {recQuery.isLoading ? (
              <div className="py-8 text-center">
                <p className="text-sm text-[var(--text-secondary)]">
                  Loading recommendations…
                </p>
              </div>
            ) : recPapers.length > 0 ? (
              <ul className="divide-y divide-[var(--divider)]">
                {recPapers.map((paper: Suggestion) => (
                  <PaperFeedRow
                    key={paper.content_id}
                    paper={paper}
                    interested={rec?.interested?.[paper.content_id] ?? []}
                    projectId={project.id}
                    canShare={canCollaborate}
                  />
                ))}
              </ul>
            ) : (
              <div className="py-8 text-center">
                <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
                  {hasFocus
                    ? "No matching papers yet. Mylo will recommend papers for this project on its next run."
                    : "Set this project's research focus so Mylo can recommend papers for it."}
                </p>
              </div>
            )}
          </Card>

          {/* Mylo's picks — the capped digest across all four areas */}
          <ProjectDigestCard digestQuery={digestQuery} />

          {/* Collections — shared reading lists the team curates together */}
          <CollectionsCard
            projectId={project.id}
            canCollaborate={canCollaborate}
          />
        </div>

        {/* RIGHT column */}
        <div className="flex flex-col gap-[22px]">
          {/* Members card */}
          <Card className="p-[22px]">
            <div className="mb-[14px] flex items-center justify-between">
              <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
                Members
              </h2>
              <span className="text-xs text-[var(--text-secondary)]">
                {project.member_count}
              </span>
            </div>

            {project.members.length === 0 ? (
              <p className="text-[12.5px] text-[var(--text-secondary)]">
                No members yet.
              </p>
            ) : (
              <div className="flex flex-col gap-[11px]">
                {project.members.map((m: ProjectMember) => (
                  <div key={m.username} className="flex items-center gap-[11px]">
                    <Avatar
                      initials={m.initials}
                      seed={m.username}
                      size={32}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="m-0 text-[13px] font-medium text-[var(--text-primary)]">
                        {m.name}
                      </p>
                      <p className="m-0 text-[11.5px] text-[var(--text-secondary)]">
                        @{m.username}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Recommended by Mylo card */}
          <Card className="p-[22px]">
            <div className="mb-[10px] flex items-center gap-2">
              <SporeNode size={16} className="text-primary" />
              <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
                Recommended by Mylo
              </h2>
            </div>
            {recQuery.isLoading ? (
              <p className="m-0 text-[12.5px] text-[var(--text-secondary)]">
                Loading recommendations…
              </p>
            ) : recTotal === 0 ? (
              <p className="m-0 text-[12.5px] text-[var(--text-secondary)]">
                {hasFocus
                  ? "Recommendations arrive after Mylo's next run."
                  : "Set this project's focus so Mylo can find matching work."}
              </p>
            ) : (
              <ul className="flex flex-col gap-[13px]">
                {miniRecs.map((r) => (
                  <MiniRecRow key={r.key} rec={r} />
                ))}
              </ul>
            )}
          </Card>

          {/* Status card */}
          <Card className="p-[22px]">
            <h2 className="mb-[12px] text-[15px] font-semibold text-[var(--text-primary)]">
              Status
            </h2>

            {project.progress !== null ? (
              <>
                <div className="mb-[7px] flex justify-between text-xs">
                  <span className="font-medium text-[var(--text-secondary)]">
                    Progress
                  </span>
                  <span className="font-semibold text-[var(--text-secondary)]">
                    {project.progress}%
                  </span>
                </div>
                <ProgressBar value={project.progress} className="mb-[14px]" />
              </>
            ) : (
              <p className="mb-[14px] text-[12.5px] text-[var(--text-secondary)]">
                Not tracked yet
              </p>
            )}

            <div className="flex items-start gap-[9px] text-[12.5px] leading-[1.5] text-[var(--text-secondary)]">
              <TargetIcon
                size={15}
                className="mt-[1px] shrink-0 text-brand-secondary"
              />
              <span>Linked to: {goalLabel ?? "—"}</span>
            </div>
          </Card>

          {/* Settings — watch categories + archive, editors only */}
          {canEditProject ? <ProjectSettingsCard project={project} /> : null}
        </div>
      </div>
    </div>
  );
}

/** The four categories Mylo can track for a project, with the icon used for
 * each area elsewhere in the portal (nav, stat cards). */
const WATCH_CATEGORY_OPTIONS: {
  key: BriefingCategory;
  label: string;
  icon: React.ReactNode;
}[] = [
  { key: "papers", label: "Papers", icon: <DocumentIcon size={15} /> },
  { key: "grants", label: "Grants", icon: <BankIcon size={15} /> },
  { key: "fellowships", label: "Fellowships", icon: <SparkleIcon size={15} /> },
  { key: "conferences", label: "Conferences", icon: <ConferenceIcon size={15} /> },
];

/**
 * Editor-only settings: which categories Mylo tracks for this project (a
 * toggle per category, saved immediately) and an archive/unarchive control.
 * Only rendered for the project's owner or lab manager — never a plain
 * collaborator, matching the backend's edit gate.
 */
function ProjectSettingsCard({ project }: { project: Project }) {
  const updateCategories = useUpdateProjectCategories();
  const archive = useArchiveProject();
  const unarchive = useUnarchiveProject();
  const [archiveError, setArchiveError] = React.useState<string | null>(null);

  const toggleCategory = (key: BriefingCategory) => {
    if (updateCategories.isPending) {
      return;
    }
    const next = project.watch_categories.includes(key)
      ? project.watch_categories.filter((c) => c !== key)
      : [...project.watch_categories, key];
    updateCategories.mutate({ id: project.id, categories: next });
  };

  const handleArchiveToggle = () => {
    setArchiveError(null);
    if (project.is_archived) {
      unarchive.mutate(project.id, {
        onError: (err) => {
          setArchiveError(
            err instanceof ProjectCapReachedError
              ? `Restoring this project would exceed your plan's limit of ${err.cap} projects — archive another first, or upgrade.`
              : (err as Error).message,
          );
        },
      });
    } else {
      archive.mutate(project.id, {
        onError: (err) => setArchiveError((err as Error).message),
      });
    }
  };

  return (
    <Card className="p-[22px]">
      <h2 className="mb-[3px] text-[15px] font-semibold text-[var(--text-primary)]">
        Mylo settings
      </h2>
      <p className="mb-[14px] text-[12.5px] text-[var(--text-secondary)]">
        Choose which areas Mylo tracks for this project.
      </p>

      <div className="flex flex-col gap-2">
        {WATCH_CATEGORY_OPTIONS.map((option) => {
          const on = project.watch_categories.includes(option.key);
          return (
            <div
              key={option.key}
              className="flex items-center justify-between gap-3 rounded-lg bg-surface-alt px-3 py-2.5"
            >
              <span className="flex items-center gap-2 text-[13px] font-medium text-[var(--text-primary)]">
                {option.icon}
                {option.label}
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={option.label}
                onClick={() => toggleCategory(option.key)}
                disabled={updateCategories.isPending}
                className={cn(
                  "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-60",
                  on ? "bg-primary" : "bg-border",
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 h-5 w-5 rounded-full bg-card shadow transition-all",
                    on ? "left-[22px]" : "left-0.5",
                  )}
                />
              </button>
            </div>
          );
        })}
      </div>
      {updateCategories.isError ? (
        <p className="mt-2 text-[11.5px] text-clay" role="alert">
          Couldn&apos;t update — try again.
        </p>
      ) : null}

      <div className="mt-4 border-t border-[var(--divider)] pt-4">
        <button
          type="button"
          onClick={handleArchiveToggle}
          disabled={archive.isPending || unarchive.isPending}
          className="w-full rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt disabled:opacity-50"
        >
          {project.is_archived
            ? unarchive.isPending
              ? "Restoring…"
              : "Unarchive project"
            : archive.isPending
              ? "Archiving…"
              : "Archive project"}
        </button>
        {archiveError ? (
          <p className="mt-2 text-[11.5px] text-clay" role="alert">
            {archiveError}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

/** One group of digest picks ("Papers", "Grants", …) — hidden when empty. */
function DigestGroup<T extends { content_id: string }>({
  title,
  items,
  render,
}: {
  title: string;
  items: T[];
  render: (item: T) => React.ReactNode;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {title} <span className="text-[var(--text-secondary)]">({items.length})</span>
      </p>
      <div className="space-y-3">{items.map(render)}</div>
    </div>
  );
}

/**
 * "Mylo's picks for this project" — the capped digest (top 10 papers / 5
 * grants / 5 fellowships / 5 conferences) reusing each area's own feed card so
 * a project's picks read exactly like the personal/lab pages, complete with
 * match percent and Mylo's reason.
 */
function ProjectDigestCard({
  digestQuery,
}: {
  digestQuery: ReturnType<typeof useProjectDigest>;
}) {
  const digest = digestQuery.data;
  const papers: Suggestion[] = digest?.papers ?? [];
  const grants: GrantOpportunity[] = digest?.grants ?? [];
  const fellowships: FellowshipOpportunity[] = digest?.fellowships ?? [];
  const conferences: ConferenceOpportunity[] = digest?.conferences ?? [];
  const total = papers.length + grants.length + fellowships.length + conferences.length;

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-[var(--divider)] px-5 pb-[14px] pt-[18px]">
        <div className="flex items-center gap-2">
          <SporeNode size={16} className="text-primary" />
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            Mylo&apos;s picks for this project
          </h2>
        </div>
        <p className="mt-[3px] text-[12.5px] text-[var(--text-secondary)]">
          The best-matching papers, grants, fellowships, and conferences for
          this project&apos;s focus.
        </p>
      </div>

      {digestQuery.isLoading ? (
        <div className="space-y-3 p-5">
          <div className="h-24 animate-pulse rounded-xl bg-surface-alt" />
          <div className="h-24 animate-pulse rounded-xl bg-surface-alt" />
        </div>
      ) : digestQuery.isError ? (
        <div className="py-8 text-center">
          <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
            Couldn&apos;t load Mylo&apos;s picks for this project.
          </p>
        </div>
      ) : total === 0 ? (
        <div className="py-8 text-center">
          <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
            Mylo is still gathering picks for this project.
          </p>
        </div>
      ) : (
        <div className="space-y-6 p-5">
          <DigestGroup
            title="Papers"
            items={papers}
            render={(paper) => (
              <SuggestionCard key={paper.content_id} suggestion={paper} />
            )}
          />
          <DigestGroup
            title="Grants"
            items={grants}
            render={(grant) => <GrantRow key={grant.content_id} grant={grant} />}
          />
          <DigestGroup
            title="Fellowships"
            items={fellowships}
            render={(item) => <FellowshipRow key={item.content_id} item={item} />}
          />
          <DigestGroup
            title="Conferences"
            items={conferences}
            render={(conf) => <ConferenceCard key={conf.content_id} conf={conf} />}
          />
        </div>
      )}
    </Card>
  );
}

/** A small percent-match chip; muted when the model left the match unscored. */
function MatchChip({ match }: { match: number | null }) {
  if (match === null) return null;
  return (
    <span className="shrink-0 rounded-full bg-surface-alt px-2 py-[2px] text-[11px] font-semibold text-[var(--text-secondary)]">
      {match}% match
    </span>
  );
}

/**
 * The paste-a-link row at the top of the project feed. Controlled input +
 * submit that resolves a DOI/article link into a project share. Disabled
 * (with a hint) when the caller isn't a project member, since the backend
 * 403s an ingest attempt from a non-participant.
 */
function IngestLinkForm({
  projectId,
  canIngest,
}: {
  projectId: string;
  canIngest: boolean;
}) {
  const ingest = useIngestProjectLink();
  const [rawInput, setRawInput] = React.useState("");
  const [result, setResult] = React.useState<{
    title: string;
    embedStatus: "ok" | "no_abstract";
  } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = rawInput.trim();
    if (!value || !canIngest || ingest.isPending) {
      return;
    }
    setError(null);
    setResult(null);
    ingest.mutate(
      { id: projectId, rawInput: value },
      {
        onSuccess: (data) => {
          setResult({ title: data.title, embedStatus: data.embed_status });
          setRawInput("");
        },
        onError: (e2) => setError((e2 as Error).message),
      },
    );
  };

  return (
    <form onSubmit={submit}>
      <div className="flex gap-2">
        <label
          className={
            canIngest
              ? "flex flex-1 items-center gap-2 rounded-[10px] border border-border bg-surface-alt px-[13px] py-2 focus-within:ring-2 focus-within:ring-ring"
              : "flex flex-1 cursor-not-allowed items-center gap-2 rounded-[10px] border border-border bg-surface-alt px-[13px] py-2 opacity-60"
          }
        >
          <LinkIcon size={15} className="shrink-0 text-[var(--text-secondary)]" />
          <input
            value={rawInput}
            onChange={(e) => setRawInput(e.target.value)}
            placeholder="Paste a DOI or article link…"
            disabled={!canIngest || ingest.isPending}
            aria-label="Paste a DOI or article link"
            className="min-w-0 flex-1 border-none bg-transparent font-[inherit] text-[13px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] disabled:cursor-not-allowed"
          />
        </label>
        <button
          type="submit"
          disabled={!canIngest || ingest.isPending || !rawInput.trim()}
          title={canIngest ? undefined : "Join this project to add papers"}
          className="shrink-0 rounded-[10px] bg-primary px-4 py-2 text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {ingest.isPending ? "Resolving…" : "Add"}
        </button>
      </div>
      {!canIngest ? (
        <p className="mt-1.5 text-[11.5px] text-[var(--text-secondary)]">
          Join this project to add papers.
        </p>
      ) : null}
      {result ? (
        <p className="mt-2 text-[12.5px] text-primary">
          Added &ldquo;{result.title}&rdquo;
          {result.embedStatus === "no_abstract"
            ? " — no abstract found, so Mylo can't match on it yet."
            : "."}
        </p>
      ) : null}
      {error ? (
        <p className="mt-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

/**
 * Quiet thumbs-up / thumbs-down icon buttons that feed the project's
 * engagement signal (`RelevanceEvent`). Local-only pressed state — there's no
 * read-back endpoint, so a click just optimistically marks itself active.
 * Hidden entirely for non-collaborators, since the backend 403s the event.
 */
function EngagementButtons({
  projectId,
  contentId,
  canCollaborate,
}: {
  projectId: string;
  contentId: string;
  canCollaborate: boolean;
}) {
  const [pressed, setPressed] = React.useState<"up" | "down" | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  if (!canCollaborate) {
    return null;
  }

  const act = (action: "thumbs_up" | "thumbs_down", next: "up" | "down") => {
    setError(null);
    recordProjectEvent(projectId, contentId, action)
      .then(() => setPressed(next))
      .catch((e) => setError((e as Error).message));
  };

  return (
    <span className="inline-flex items-center gap-0.5">
      <button
        type="button"
        onClick={() => act("thumbs_up", "up")}
        aria-pressed={pressed === "up"}
        aria-label="Mark helpful"
        title="Helpful"
        className={cn(
          "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          pressed === "up" &&
            "bg-[color-mix(in_srgb,var(--primary)_14%,transparent)] text-primary",
        )}
      >
        <ThumbsUpIcon size={13} />
      </button>
      <button
        type="button"
        onClick={() => act("thumbs_down", "down")}
        aria-pressed={pressed === "down"}
        aria-label="Mark not helpful"
        title="Not helpful"
        className={cn(
          "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          pressed === "down" && "bg-clay-soft text-clay",
        )}
      >
        <ThumbsDownIcon size={13} />
      </button>
      {error ? (
        <span className="text-[11px] text-clay" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}

/**
 * A compact popover that adds a content item to one of the project's
 * collections. Lists the caller's existing lists (fetched lazily, only while
 * open) and lets them pick one; the click both adds the item and closes the
 * popover. Hidden for non-collaborators, since the backend 403s the write.
 */
function AddToCollectionButton({
  projectId,
  contentId,
  canCollaborate,
}: {
  projectId: string;
  contentId: string;
  canCollaborate: boolean;
}) {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const collectionsQuery = useProjectCollections(open ? projectId : undefined);
  const add = useAddToCollection(projectId);
  const [added, setAdded] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  if (!canCollaborate) {
    return null;
  }

  const collections = collectionsQuery.data?.items ?? [];

  const handleAdd = (collection: CollectionBrief) => {
    setError(null);
    add.mutate(
      { collectionId: collection.id, contentId },
      {
        onSuccess: () => {
          setAdded(collection.name);
          setOpen(false);
        },
        onError: (e) => setError((e as Error).message),
      },
    );
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={added ? `Added to ${added}` : "Add to a list"}
        title={added ? `Added to ${added}` : "Add to a list"}
        className={cn(
          "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          added && "text-primary",
        )}
      >
        <ListIcon size={13} />
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Add to a list"
          className="absolute right-0 top-8 z-30 w-[220px] rounded-xl border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
        >
          {collectionsQuery.isLoading ? (
            <p className="px-2.5 py-2 text-[12px] text-[var(--text-secondary)]">
              Loading lists…
            </p>
          ) : collections.length === 0 ? (
            <p className="px-2.5 py-2 text-[12px] text-[var(--text-secondary)]">
              No lists yet — start one in Collections below.
            </p>
          ) : (
            <ul className="max-h-[180px] overflow-y-auto">
              {collections.map((collection) => (
                <li key={collection.id}>
                  <button
                    type="button"
                    onClick={() => handleAdd(collection)}
                    disabled={add.isPending}
                    className="w-full truncate rounded-lg px-2.5 py-1.5 text-left text-[12.5px] text-[var(--text-primary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  >
                    {collection.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {error ? (
            <p className="px-2.5 pb-1 pt-0.5 text-[11px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * A small action button that shares a recommendation into the project's team
 * feed. Idle → pending ("Sharing…") → success ("Shared"); an error renders
 * inline rather than blocking the row.
 */
function ShareToProjectButton({
  projectId,
  contentId,
}: {
  projectId: string;
  contentId: string;
}) {
  const share = useShareToProject();
  const [shared, setShared] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const handleClick = () => {
    if (share.isPending) return;
    setError(null);
    share.mutate(
      { id: projectId, contentId },
      {
        onSuccess: () => setShared(true),
        onError: (e) => setError((e as Error).message),
      },
    );
  };

  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        type="button"
        onClick={handleClick}
        disabled={share.isPending || shared}
        aria-label={shared ? "Shared to the project feed" : "Share to the project feed"}
        className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:border-[color-mix(in_srgb,var(--accent)_45%,transparent)] hover:bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-70"
      >
        {shared ? "Shared" : share.isPending ? "Sharing…" : "Share"}
      </button>
      {error ? (
        <span className="text-[11px] text-clay" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}

/**
 * One recommended paper in the project feed (title, source, Mylo's reason).
 * When `canShare` and a `projectId` are given, a "Share" action pushes this
 * pick into the team's shared feed.
 */
function PaperFeedRow({
  paper,
  interested,
  projectId,
  canShare,
}: {
  paper: Suggestion;
  interested: InterestedMember[];
  projectId?: string;
  canShare?: boolean;
}) {
  return (
    <li className="px-5 py-[14px]">
      <div className="flex items-start justify-between gap-3">
        {paper.url ? (
          <a
            href={paper.url}
            target="_blank"
            rel="noreferrer"
            className="text-[14px] font-semibold leading-snug text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {paper.title}
          </a>
        ) : (
          <span className="text-[14px] font-semibold leading-snug text-[var(--text-primary)]">
            {paper.title}
          </span>
        )}
        <div className="flex shrink-0 items-center gap-1.5">
          <MatchChip match={paper.match_percent} />
          {canShare && projectId ? (
            <>
              <EngagementButtons
                projectId={projectId}
                contentId={paper.content_id}
                canCollaborate={canShare}
              />
              <AddToCollectionButton
                projectId={projectId}
                contentId={paper.content_id}
                canCollaborate={canShare}
              />
              <ShareToProjectButton
                projectId={projectId}
                contentId={paper.content_id}
              />
            </>
          ) : null}
        </div>
      </div>
      {paper.source ? (
        <p className="mt-1 text-[11.5px] uppercase tracking-wide text-[var(--text-secondary)]">
          {paper.source}
        </p>
      ) : null}
      {paper.reason ? (
        <p className="mt-1.5 text-[12.5px] leading-[1.5] text-[var(--text-secondary)]">
          {paper.reason}
        </p>
      ) : null}
      <InterestedRow members={interested} />
    </li>
  );
}

/** "Also interested" — lab members who personally matched this same item. */
function InterestedRow({ members }: { members: InterestedMember[] }) {
  if (members.length === 0) return null;
  const shown = members.slice(0, 4);
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] font-medium text-[var(--text-secondary)]">
        Also interested:
      </span>
      {shown.map((m) => (
        <span
          key={m.username}
          title={`${m.name} · ${m.match_percent}% match`}
          className="inline-flex items-center gap-1.5 rounded-full bg-surface-alt px-2 py-[2px] text-[11px] font-medium text-[var(--text-secondary)]"
        >
          <Avatar initials={m.initials} seed={m.username} size={16} />
          {m.name}
        </span>
      ))}
      {members.length > shown.length ? (
        <span className="text-[11px] text-[var(--text-secondary)]">
          +{members.length - shown.length} more
        </span>
      ) : null}
    </div>
  );
}

/**
 * One row in the team's shared feed: the paper, who shared it (+ their note),
 * how many others also shared it, and how many members have seen it. Clicking
 * the outbound link marks the item seen (fire-and-forget) so the seen count
 * reflects real views.
 */
function FeedItemRow({
  item,
  projectId,
  canCollaborate,
}: {
  item: ProjectFeedItem;
  projectId: string;
  canCollaborate: boolean;
}) {
  const markSeen = () => {
    markProjectItemSeen(projectId, item.content_id).catch(() => {
      // Best-effort view tracking — a failed ping shouldn't block navigation.
    });
  };

  const meta = [
    item.venue || null,
    item.year ? String(item.year) : null,
    item.authors.length > 0 ? item.authors.slice(0, 3).join(", ") : null,
  ].filter(Boolean);

  const otherSharers = item.co_sharers.slice(0, 3);

  return (
    <li className="px-5 py-[14px]">
      <div className="flex items-start justify-between gap-3">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            onClick={markSeen}
            className="text-[14px] font-semibold leading-snug text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {item.title}
          </a>
        ) : (
          <span className="text-[14px] font-semibold leading-snug text-[var(--text-primary)]">
            {item.title}
          </span>
        )}
        <div className="flex shrink-0 items-center gap-1.5">
          {item.seen && item.seen.seen_by_count > 0 ? (
            <Pill tone="neutral" className="shrink-0">
              Seen by {item.seen.seen_by_count}
            </Pill>
          ) : null}
          <EngagementButtons
            projectId={projectId}
            contentId={item.content_id}
            canCollaborate={canCollaborate}
          />
          <AddToCollectionButton
            projectId={projectId}
            contentId={item.content_id}
            canCollaborate={canCollaborate}
          />
        </div>
      </div>

      {item.source ? (
        <p className="mt-1 text-[11.5px] uppercase tracking-wide text-[var(--text-secondary)]">
          {item.source}
        </p>
      ) : null}
      {meta.length > 0 ? (
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
          {meta.join(" · ")}
        </p>
      ) : null}

      <div className="mt-2.5 flex items-center gap-2">
        <Avatar
          initials={item.shared_by.initials}
          seed={item.shared_by.username}
          size={20}
        />
        <span className="text-[12.5px] font-medium text-[var(--text-secondary)]">
          {item.shared_by.name}
        </span>
        <span className="text-[11px] text-[var(--text-secondary)]">
          shared {relativeTime(item.shared_at)}
        </span>
      </div>

      {item.note ? (
        <p className="mt-1.5 pl-[28px] text-[12.5px] leading-[1.5] text-[var(--text-secondary)]">
          &ldquo;{item.note}&rdquo;
        </p>
      ) : null}

      {item.share_count > 1 ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5 pl-[28px]">
          <span className="text-[11px] font-medium text-[var(--text-secondary)]">
            +{item.share_count - 1} also shared:
          </span>
          {otherSharers.map((m) => (
            <span
              key={m.username}
              title={m.name}
              className="inline-flex items-center gap-1.5 rounded-full bg-surface-alt px-2 py-[2px] text-[11px] font-medium text-[var(--text-secondary)]"
            >
              <Avatar initials={m.initials} seed={m.username} size={16} />
              {m.name}
            </span>
          ))}
          {item.co_sharers.length > otherSharers.length ? (
            <span className="text-[11px] text-[var(--text-secondary)]">
              +{item.co_sharers.length - otherSharers.length} more
            </span>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** One compact cross-area recommendation in the sidebar card. */
function MiniRecRow({ rec }: { rec: MiniRec }) {
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          {rec.area}
        </span>
        <MatchChip match={rec.match} />
      </div>
      {rec.url ? (
        <a
          href={rec.url}
          target="_blank"
          rel="noreferrer"
          className="text-[13px] font-medium leading-snug text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {rec.title}
        </a>
      ) : (
        <span className="text-[13px] font-medium leading-snug text-[var(--text-primary)]">
          {rec.title}
        </span>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Collections — shared reading lists the project's team curates together.
// ---------------------------------------------------------------------------

/**
 * The "Collections" card on the project page: the team's shared, non-archived
 * reading lists plus an inline create form. Each row expands to show and
 * manage the list's items.
 */
function CollectionsCard({
  projectId,
  canCollaborate,
}: {
  projectId: string;
  canCollaborate: boolean;
}) {
  const { data, isLoading, isError } = useProjectCollections(projectId);
  const collections = data?.items ?? [];
  const [showCreate, setShowCreate] = React.useState(false);
  const [expandedId, setExpandedId] = React.useState<string | null>(null);

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-[var(--divider)] px-5 pb-[14px] pt-[18px]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="mb-[3px] text-base font-semibold text-[var(--text-primary)]">
              Collections
            </h2>
            <p className="text-[12.5px] text-[var(--text-secondary)]">
              Shared reading lists the team curates together.
            </p>
          </div>
          {canCollaborate ? (
            <button
              type="button"
              onClick={() => setShowCreate((v) => !v)}
              aria-expanded={showCreate}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <PlusIcon size={13} />
              New list
            </button>
          ) : null}
        </div>

        {showCreate ? (
          <CreateCollectionForm
            projectId={projectId}
            onDone={() => setShowCreate(false)}
          />
        ) : null}
      </div>

      {isLoading ? (
        <div className="py-8 text-center">
          <p className="text-sm text-[var(--text-secondary)]">
            Loading collections…
          </p>
        </div>
      ) : isError ? (
        <div className="py-8 text-center">
          <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
            Couldn&apos;t load the project&apos;s collections.
          </p>
        </div>
      ) : collections.length === 0 ? (
        <div className="py-8 text-center">
          <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-secondary)]">
            {canCollaborate
              ? "No lists yet. Start one to group papers the team wants to revisit."
              : "No shared lists yet."}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-[var(--divider)]">
          {collections.map((collection) => (
            <CollectionRow
              key={collection.id}
              collection={collection}
              projectId={projectId}
              canCollaborate={canCollaborate}
              expanded={expandedId === collection.id}
              onToggle={() =>
                setExpandedId((cur) =>
                  cur === collection.id ? null : collection.id,
                )
              }
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The inline "New list" form: a name and an optional description. */
function CreateCollectionForm({
  projectId,
  onDone,
}: {
  projectId: string;
  onDone: () => void;
}) {
  const create = useCreateCollection(projectId);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = name.trim();
    if (!value || create.isPending) {
      return;
    }
    setError(null);
    create.mutate(
      { name: value, description: description.trim() || undefined },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          onDone();
        },
        onError: (e2) => setError((e2 as Error).message),
      },
    );
  };

  return (
    <form className="mt-3 flex flex-col gap-2" onSubmit={submit}>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="List name"
        aria-label="List name"
        className={INPUT}
      />
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description (optional)"
        aria-label="List description"
        className={INPUT}
      />
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={create.isPending || !name.trim()}
          className="inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create list"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Cancel
        </button>
      </div>
      {error ? (
        <p className="text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

/**
 * One collection row: name, item count, creator avatar, and a chevron that
 * expands it to show and manage the list's items. When expanded and
 * `canCollaborate`, offers a per-item remove and an archive toggle for the
 * whole list.
 */
function CollectionRow({
  collection,
  projectId,
  canCollaborate,
  expanded,
  onToggle,
}: {
  collection: CollectionBrief;
  projectId: string;
  canCollaborate: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detailQuery = useProjectCollection(
    expanded ? projectId : undefined,
    expanded ? collection.id : undefined,
  );
  const remove = useRemoveFromCollection(projectId);
  const archive = useUpdateCollection(projectId);
  const [error, setError] = React.useState<string | null>(null);

  const items = detailQuery.data?.items ?? [];

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 px-5 py-[14px] text-left transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="min-w-0">
          <span className="block truncate text-[14px] font-semibold text-[var(--text-primary)]">
            {collection.name}
          </span>
          {collection.description ? (
            <span className="block truncate text-[12px] text-[var(--text-secondary)]">
              {collection.description}
            </span>
          ) : null}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <Pill tone="neutral">
            {collection.item_count} item{collection.item_count === 1 ? "" : "s"}
          </Pill>
          {collection.created_by ? (
            <Avatar
              initials={collection.created_by.initials}
              seed={collection.created_by.username}
              size={20}
              title={collection.created_by.name}
            />
          ) : null}
          <ChevronDownIcon
            size={14}
            aria-hidden="true"
            className={cn(
              "text-[var(--text-secondary)] transition-transform duration-200 motion-reduce:transition-none",
              expanded && "rotate-180",
            )}
          />
        </span>
      </button>

      {expanded ? (
        <div className="border-t border-[var(--divider)] bg-surface-alt/60 px-5 py-3.5">
          {canCollaborate ? (
            <button
              type="button"
              onClick={() => {
                setError(null);
                archive.mutate(
                  { collectionId: collection.id, patch: { is_archived: true } },
                  { onError: (e) => setError((e as Error).message) },
                );
              }}
              disabled={archive.isPending}
              className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {archive.isPending ? "Archiving…" : "Archive list"}
            </button>
          ) : null}

          {detailQuery.isLoading ? (
            <p className="text-[12.5px] text-[var(--text-secondary)]">
              Loading items…
            </p>
          ) : detailQuery.isError ? (
            <p className="text-[12.5px] text-[var(--text-secondary)]">
              Couldn&apos;t load this list&apos;s items.
            </p>
          ) : items.length === 0 ? (
            <p className="text-[12.5px] text-[var(--text-secondary)]">
              No items in this list yet.
            </p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {items.map((item) => (
                <li
                  key={item.content_id}
                  className="flex items-start justify-between gap-3"
                >
                  <div className="min-w-0">
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[13px] font-medium leading-snug text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {item.title}
                      </a>
                    ) : (
                      <span className="text-[13px] font-medium leading-snug text-[var(--text-primary)]">
                        {item.title}
                      </span>
                    )}
                    {item.note ? (
                      <p className="mt-1 text-[12px] leading-[1.5] text-[var(--text-secondary)]">
                        &ldquo;{item.note}&rdquo;
                      </p>
                    ) : null}
                  </div>
                  {canCollaborate ? (
                    <button
                      type="button"
                      onClick={() => {
                        setError(null);
                        remove.mutate(
                          {
                            collectionId: collection.id,
                            contentId: item.content_id,
                          },
                          { onError: (e) => setError((e as Error).message) },
                        );
                      }}
                      disabled={remove.isPending}
                      aria-label={`Remove ${item.title} from ${collection.name}`}
                      title="Remove from list"
                      className="shrink-0 rounded-full p-1 text-[var(--text-secondary)] transition-colors hover:bg-surface hover:text-clay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                    >
                      <CloseIcon size={12} />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}

          {error ? (
            <p className="mt-2 text-[11.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
