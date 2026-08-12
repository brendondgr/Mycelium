"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  CloseIcon,
  LinkIcon,
  ListIcon,
  PlusIcon,
  SporeNode,
  TargetIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import {
  ProjectIdentity,
  relativeTime,
} from "@/components/portal/projects/project-identity";
import { ProjectEditorModal } from "@/components/portal/projects/project-editor-modal";
import { ProjectRecommendationTabs } from "@/components/portal/projects/project-tabs";
import { ProjectTeamCard } from "@/components/portal/projects/project-team-card";
import {
  useAddToCollection,
  useCreateCollection,
  useIngestProjectLink,
  useProject,
  useProjectCollection,
  useProjectCollections,
  useProjectFeed,
  useProjectRecommendations,
  useRemoveFromCollection,
  useShareToProject,
  useUpdateCollection,
} from "@/lib/portal/hooks";
import { markProjectItemSeen, recordProjectEvent } from "@/lib/portal/mutations";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type {
  CollectionBrief,
  InterestedMember,
  Project,
  ProjectFeedItem,
  Suggestion,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Shared input style for the small inline forms on this page. */
const INPUT =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * A project's own page: its identity, the four recommendation feeds Mylo runs
 * for it, and the team's shared workspace around them.
 *
 * The project is read by id rather than picked out of the workspace-scoped
 * project list, so a lab project opens correctly from any scope — and its own
 * payload, not the active workspace, decides whether the reader may edit it.
 */
export function ProjectDetailSection() {
  const { projects, activeProjectId, openProjectsList, labs } = usePortal();

  // The list copy paints immediately when it happens to be in scope; the read by
  // id is the authority and replaces it as soon as it lands.
  const projectQuery = useProject(activeProjectId ?? undefined);
  const project =
    projectQuery.data ?? projects.find((p) => p.id === activeProjectId);

  const recQuery = useProjectRecommendations(project?.id);
  const feedQuery = useProjectFeed(project?.id);

  const [editorOpen, setEditorOpen] = React.useState(false);
  const teamRef = React.useRef<HTMLDivElement | null>(null);

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
        {projectQuery.isError ? (
          <p className="text-sm text-[var(--text-secondary)]">
            This project isn&apos;t available — it may have been archived, or you
            may no longer have access to it.
          </p>
        ) : (
          <div className="space-y-4" aria-hidden>
            <div className="h-[150px] animate-pulse rounded-2xl bg-surface-alt" />
            <div className="h-[320px] animate-pulse rounded-2xl bg-surface-alt" />
          </div>
        )}
      </div>
    );
  }

  const feedItems = feedQuery.data?.items ?? [];
  const recPapers = recQuery.data?.papers ?? [];
  const hasFocus = project.focus.areas.length > 0;
  // Who may write into the project: its members, a personal project's owner, or
  // a lab project's owner/admin/PI — the backend's participant gate, mirrored so
  // the UI hides an action rather than letting it 403.
  const canCollaborate =
    project.is_member || project.scope === "user" || project.can_edit;
  // The owning lab, when the reader belongs to it — only used for the logo mark,
  // so an outside collaborator simply gets the text badge.
  const lab = labs.find((l) => l.slug === project.scope_slug) ?? null;

  return (
    <div>
      {backButton}

      <ProjectIdentity
        project={project}
        lab={lab}
        onEdit={() => setEditorOpen(true)}
        onManageMembers={() =>
          teamRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
        }
      />

      <div className="grid items-start gap-[22px] lg:grid-cols-[1.55fr_1fr]">
        {/* LEFT — what Mylo found, then what the team has done with it. */}
        <div className="flex flex-col gap-[22px]">
          <ProjectRecommendationTabs
            project={project}
            data={recQuery.data}
            isLoading={recQuery.isLoading}
            isError={recQuery.isError}
          />

          {/* The team's shared feed */}
          <Card className="overflow-hidden">
            <div className="border-b border-[var(--divider)] px-5 pb-[14px] pt-[18px]">
              <h2 className="mb-[3px] text-base font-semibold text-[var(--text-primary)]">
                Shared by the team
              </h2>
              <p className="mb-[14px] text-[12.5px] text-[var(--text-secondary)]">
                Papers the team has pushed into this project, plus articles you
                paste in directly.
              </p>

              <IngestLinkForm projectId={project.id} canIngest={canCollaborate} />
            </div>

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
                  No shared papers yet — paste a link above, or push one of
                  Mylo&apos;s picks into the feed below.
                </p>
              </div>
            )}

            {/* Mylo's top picks, ready to push into the shared feed. */}
            <div className="border-t border-[var(--divider)] px-5 pb-[8px] pt-[16px]">
              <h3 className="mb-[3px] text-[13px] font-semibold text-[var(--text-primary)]">
                Share one of Mylo&apos;s picks
              </h3>
              <p className="text-[11.5px] text-[var(--text-secondary)]">
                The strongest paper matches for this project, one click from the
                team&apos;s feed.
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
                {recPapers.slice(0, 5).map((paper: Suggestion) => (
                  <PaperFeedRow
                    key={paper.content_id}
                    paper={paper}
                    interested={recQuery.data?.interested?.[paper.content_id] ?? []}
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

          {/* Collections — shared reading lists the team curates together */}
          <CollectionsCard
            projectId={project.id}
            canCollaborate={canCollaborate}
          />
        </div>

        {/* RIGHT — who is on it, and what it is aimed at. */}
        <div className="flex flex-col gap-[22px]">
          <div ref={teamRef}>
            <ProjectTeamCard project={project} />
          </div>
          <ProjectFocusCard project={project} onEdit={() => setEditorOpen(true)} />
        </div>
      </div>

      {editorOpen ? (
        <ProjectEditorModal
          project={project}
          onClose={() => setEditorOpen(false)}
        />
      ) : null}
    </div>
  );
}

/**
 * What this project is aimed at — the themes Mylo actually searches on, plus its
 * progress. A project's recommendations are only as good as this, so the page
 * shows it rather than leaving the reader guessing why a feed looks the way it
 * does.
 */
function ProjectFocusCard({
  project,
  onEdit,
}: {
  project: Project;
  onEdit: () => void;
}) {
  const { clusters, areas, watch_topics: watchTopics } = project.focus;

  return (
    <Card className="p-[22px]">
      <div className="mb-[12px] flex items-start justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
          Research focus
        </h2>
        {project.can_edit ? (
          <button
            type="button"
            onClick={onEdit}
            className="shrink-0 text-[12px] font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Edit
          </button>
        ) : null}
      </div>

      {areas.length === 0 ? (
        <p className="text-[12.5px] leading-[1.5] text-[var(--text-secondary)]">
          {project.can_edit
            ? "No focus set yet, so Mylo has nothing to search on for this project. Add one from Edit project → Focus."
            : "No focus set yet, so Mylo isn't searching for this project."}
        </p>
      ) : clusters.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {clusters.map((cluster) => (
            <li key={cluster.id}>
              <p className="m-0 flex items-center gap-1.5 text-[12.5px] font-semibold text-[var(--text-primary)]">
                <SporeNode size={12} className="text-primary" />
                {cluster.label}
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {cluster.areas.map((area) => (
                  <span
                    key={area}
                    className="rounded-full bg-surface-alt px-2 py-[2px] text-[11px] text-[var(--text-secondary)]"
                  >
                    {area}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {areas.map((area) => (
            <span
              key={area}
              className="rounded-full bg-surface-alt px-2 py-[2px] text-[11px] text-[var(--text-secondary)]"
            >
              {area}
            </span>
          ))}
        </div>
      )}

      {watchTopics.length > 0 ? (
        <div className="mt-4 flex items-start gap-[9px] border-t border-[var(--divider)] pt-3.5 text-[12px] leading-[1.5] text-[var(--text-secondary)]">
          <TargetIcon
            size={14}
            className="mt-[2px] shrink-0 text-brand-secondary"
            aria-hidden="true"
          />
          <span>
            Searching on {watchTopics.slice(0, 5).join(", ")}
            {watchTopics.length > 5 ? ` +${watchTopics.length - 5} more` : ""}.
          </span>
        </div>
      ) : null}

      {project.progress !== null ? (
        <div className="mt-4 border-t border-[var(--divider)] pt-3.5">
          <div className="mb-[7px] flex justify-between text-xs">
            <span className="font-medium text-[var(--text-secondary)]">
              Progress
            </span>
            <span className="font-semibold text-[var(--text-secondary)]">
              {project.progress}%
            </span>
          </div>
          <ProgressBar value={project.progress} />
        </div>
      ) : null}
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
