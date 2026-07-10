"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import {
  ChevronLeftIcon,
  EditIcon,
  LinkIcon,
  SporeNode,
  TargetIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import {
  displayStatus,
  statusPillTone,
} from "@/components/portal/project-status";
import {
  useIngestProjectLink,
  useProjectFeed,
  useProjectRecommendations,
  useShareToProject,
} from "@/lib/portal/hooks";
import { markProjectItemSeen } from "@/lib/portal/mutations";
import type {
  InterestedMember,
  ProjectFeedItem,
  ProjectMember,
  Suggestion,
  TargetRecommendations,
} from "@/lib/portal/types";

/** A compact, area-labelled recommendation row for the sidebar. */
type MiniRec = { key: string; area: string; title: string; match: number | null; url: string };

/** Top few recommendations across areas for the sidebar "Recommended by Mylo" card. */
function topRecommendations(rec: TargetRecommendations): MiniRec[] {
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
  const { projects, activeProjectId, openProjectsList } = usePortal();

  const project = projects.find((p) => p.id === activeProjectId);
  // Hooks must run every render (before the early return), so each takes the id
  // optionally and stays disabled until a project is selected.
  const recQuery = useProjectRecommendations(project?.id);
  const feedQuery = useProjectFeed(project?.id);

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
        <p className="text-sm text-[var(--text-muted)]">Loading project…</p>
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
            <span className="text-[12.5px] text-[var(--text-muted)]">
              updated {relativeTime(project.updated_at)}
            </span>
            {project.progress !== null && (
              <>
                <span className="text-[12.5px] text-[var(--text-muted)]">·</span>
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
          <span className="text-[var(--text-muted)]">No description yet.</span>
        )}
      </p>

      {/* Responsive two-column grid */}
      <div className="grid items-start gap-[22px] lg:grid-cols-[1.55fr_1fr]">
        {/* LEFT: Project feed */}
        <Card className="overflow-hidden">
          <div className="border-b border-[var(--divider)] px-5 pb-[14px] pt-[18px]">
            <h2 className="mb-[3px] text-base font-semibold text-[var(--text-primary)]">
              Project feed
            </h2>
            <p className="mb-[14px] text-[12.5px] text-[var(--text-muted)]">
              Papers the team has shared, plus articles you paste in directly.
            </p>

            <IngestLinkForm projectId={project.id} canIngest={canCollaborate} />
          </div>

          {/* The team's shared feed — the primary content of this card. */}
          {feedQuery.isLoading ? (
            <div className="py-8 text-center">
              <p className="text-sm text-[var(--text-muted)]">
                Loading the shared feed…
              </p>
            </div>
          ) : feedQuery.isError ? (
            <div className="py-8 text-center">
              <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-muted)]">
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
                />
              ))}
            </ul>
          ) : (
            <div className="py-8 text-center">
              <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-muted)]">
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
            <p className="text-[11.5px] text-[var(--text-muted)]">
              Mylo&apos;s picks for this project&apos;s focus.
            </p>
          </div>
          {recQuery.isLoading ? (
            <div className="py-8 text-center">
              <p className="text-sm text-[var(--text-muted)]">
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
              <p className="mx-auto max-w-[46ch] text-sm text-[var(--text-muted)]">
                {hasFocus
                  ? "No matching papers yet. Mylo will recommend papers for this project on its next run."
                  : "Set this project's research focus so Mylo can recommend papers for it."}
              </p>
            </div>
          )}
        </Card>

        {/* RIGHT column */}
        <div className="flex flex-col gap-[22px]">
          {/* Members card */}
          <Card className="p-[22px]">
            <div className="mb-[14px] flex items-center justify-between">
              <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
                Members
              </h2>
              <span className="text-xs text-[var(--text-muted)]">
                {project.member_count}
              </span>
            </div>

            {project.members.length === 0 ? (
              <p className="text-[12.5px] text-[var(--text-muted)]">
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
                      <p className="m-0 text-[11.5px] text-[var(--text-muted)]">
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
              <p className="m-0 text-[12.5px] text-[var(--text-muted)]">
                Loading recommendations…
              </p>
            ) : recTotal === 0 ? (
              <p className="m-0 text-[12.5px] text-[var(--text-muted)]">
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
              <p className="mb-[14px] text-[12.5px] text-[var(--text-muted)]">
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
        </div>
      </div>
    </div>
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
          <LinkIcon size={15} className="shrink-0 text-[var(--text-muted)]" />
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
        <p className="mt-1.5 text-[11.5px] text-[var(--text-muted)]">
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
        <div className="flex shrink-0 items-center gap-2">
          <MatchChip match={paper.match_percent} />
          {canShare && projectId ? (
            <ShareToProjectButton
              projectId={projectId}
              contentId={paper.content_id}
            />
          ) : null}
        </div>
      </div>
      {paper.source ? (
        <p className="mt-1 text-[11.5px] uppercase tracking-wide text-[var(--text-muted)]">
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
      <span className="text-[11px] font-medium text-[var(--text-muted)]">
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
        <span className="text-[11px] text-[var(--text-muted)]">
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
}: {
  item: ProjectFeedItem;
  projectId: string;
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
        {item.seen && item.seen.seen_by_count > 0 ? (
          <Pill tone="neutral" className="shrink-0">
            Seen by {item.seen.seen_by_count}
          </Pill>
        ) : null}
      </div>

      {item.source ? (
        <p className="mt-1 text-[11.5px] uppercase tracking-wide text-[var(--text-muted)]">
          {item.source}
        </p>
      ) : null}
      {meta.length > 0 ? (
        <p className="mt-1 text-[12px] text-[var(--text-muted)]">
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
        <span className="text-[11px] text-[var(--text-muted)]">
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
          <span className="text-[11px] font-medium text-[var(--text-muted)]">
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
            <span className="text-[11px] text-[var(--text-muted)]">
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
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
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
