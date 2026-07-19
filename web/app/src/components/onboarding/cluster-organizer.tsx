"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/portal/primitives/card";
import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import { proposeClusters } from "@/lib/auth-client";
import type { ClusterGroup } from "@/lib/auth-types";
import { cn } from "@/lib/utils";

/** UI/validation sanity cap on clusters per profile — mirrors the backend's
 * `MAX_CLUSTERS` (apps.content.clustering, Open Decision D-C3). */
const MAX_CLUSTERS = 6;

/** Client-side sentinel for the "Unsorted" tray — never sent to the backend
 * and never appears in a `ClusterGroup.id`. */
const UNSORTED_ID = "__unsorted__";

type MenuItem = { key: string; label: string };

export type ClusterOrganizerProps = {
  /** The full set of declared areas — the source of truth for membership. */
  areas: string[];
  /** Current clusters (may be empty). */
  clusters: ClusterGroup[];
  keywords?: string[];
  statement?: string;
  /** Fires on every edit with the new, sanitized clusters array. */
  onChange: (clusters: ClusterGroup[]) => void;
  /** Fires when a propose/sort call returns a watch-topic seed. */
  onWatchSeed?: (topics: string[]) => void;
  /** Fires with the new full area list when the user adds / renames / removes an
   * interest inside the organizer. When omitted, the area list is read-only and
   * only the move affordances show (the organizer can't invent or drop areas). */
  onAreasChange?: (areas: string[]) => void;
  /** Tier cap on how many clusters may exist (defaults to the structural max). */
  maxClusters?: number;
  /** Tier cap on how many interests one cluster may hold (defaults to no limit).
   * The Free plan sets this to 2, so a cluster is a tight "one search, two terms". */
  maxTopicsPerCluster?: number;
};

/**
 * Force `clusters` under the tier caps: keep at most `maxClusters` clusters, and
 * at most `maxTopicsPerCluster` areas in each. Anything trimmed simply loses its
 * membership and falls back to the Unsorted tray (no area is ever deleted). Used
 * to clamp an LLM proposal or a pre-cap saved grouping before it reaches the UI.
 */
export function clampClustersToCaps(
  clusters: ClusterGroup[],
  { maxClusters, maxTopicsPerCluster }: { maxClusters: number; maxTopicsPerCluster: number },
): ClusterGroup[] {
  return clusters.slice(0, maxClusters).map((cluster) => ({
    ...cluster,
    areas: cluster.areas.slice(0, maxTopicsPerCluster),
  }));
}

/**
 * A stable, collision-free slug for a **new** cluster: `c-<slug-of-label>`,
 * disambiguated against `existing` ids. Mirrors the backend's
 * `apps.content.clustering.make_cluster_id` — only for clusters being created
 * for the first time; an existing cluster's id is never regenerated.
 */
function makeClusterId(label: string, existing: string[]): string {
  const base = slugify(label) || "cluster";
  const candidate = `c-${base}`;
  if (!existing.includes(candidate)) {
    return candidate;
  }
  let n = 2;
  while (existing.includes(`${candidate}-${n}`)) {
    n += 1;
  }
  return `${candidate}-${n}`;
}

function slugify(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "") // strip combining diacritics (ascii-fold)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

/**
 * Coerce `clusters` into a valid partition of `areas`: drops memberships for
 * areas no longer declared, and keeps only the first cluster to claim a
 * duplicated area. Applied both for display (so a removed area disappears and
 * a renamed cluster keeps its id) and before every `onChange` call, so the
 * invariant — cluster areas are always a subset of `areas`, no area in two
 * clusters — holds no matter what the caller passes in.
 */
function sanitizeClusters(clusters: ClusterGroup[], areas: string[]): ClusterGroup[] {
  const areaSet = new Set(areas);
  const seen = new Set<string>();
  return clusters.map((cluster) => {
    const kept: string[] = [];
    for (const area of cluster.areas) {
      if (areaSet.has(area) && !seen.has(area)) {
        seen.add(area);
        kept.push(area);
      }
    }
    return { ...cluster, areas: kept };
  });
}

/** Areas not currently claimed by any (sanitized) cluster — the Unsorted tray. */
function computeUnsorted(sanitized: ClusterGroup[], areas: string[]): string[] {
  const assigned = new Set(sanitized.flatMap((cluster) => cluster.areas));
  return areas.filter((area) => !assigned.has(area));
}

/**
 * The "Organize your interests" surface: cluster cards with rename/delete,
 * an Unsorted tray, drag-and-drop plus an accessible "Move to" menu for
 * reassigning areas, merge/split, and Mylo-assisted propose/sort. Presentational
 * plus local UI state only — the parent owns `areas`/`clusters` via props and
 * `onChange`.
 */
export function ClusterOrganizer({
  areas,
  clusters,
  keywords,
  statement,
  onChange,
  onWatchSeed,
  onAreasChange,
  maxClusters,
  maxTopicsPerCluster,
}: ClusterOrganizerProps) {
  const canEditAreas = typeof onAreasChange === "function";
  // Effective caps — a missing prop means "structural default / no tier limit".
  const clusterLimit = maxClusters ?? MAX_CLUSTERS;
  const perClusterLimit = maxTopicsPerCluster ?? Infinity;
  const hasPerClusterLimit = Number.isFinite(perClusterLimit);
  const sanitized = useMemo(
    () => sanitizeClusters(clusters, areas),
    [clusters, areas],
  );
  const unsorted = useMemo(
    () => computeUnsorted(sanitized, areas),
    [sanitized, areas],
  );

  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [busy, setBusy] = useState<"propose" | "sort" | null>(null);
  const [error, setError] = useState<string | null>(null);

  function emit(next: ClusterGroup[]) {
    onChange(sanitizeClusters(next, areas));
  }

  /** Whether `cluster` is already at the per-cluster interest cap. */
  function isClusterFull(cluster: ClusterGroup): boolean {
    return hasPerClusterLimit && cluster.areas.length >= perClusterLimit;
  }

  /** The "cluster is full" message shown when a move/add is blocked by the cap. */
  const clusterFullMessage = `Each cluster can hold up to ${perClusterLimit} ${
    perClusterLimit === 1 ? "topic" : "topics"
  } on your plan. Remove one first, or upgrade to widen a search.`;

  function handleRename(id: string, label: string) {
    emit(sanitized.map((cluster) => (cluster.id === id ? { ...cluster, label } : cluster)));
  }

  function handleCreate() {
    if (sanitized.length >= clusterLimit) {
      return;
    }
    const id = makeClusterId("New cluster", sanitized.map((cluster) => cluster.id));
    emit([...sanitized, { id, label: "New cluster", areas: [] }]);
  }

  function handleDelete(id: string) {
    // Delete any cluster, empty or not — its areas simply fall back to the
    // Unsorted tray (nothing is lost), so the user keeps full control.
    emit(sanitized.filter((cluster) => cluster.id !== id));
  }

  /** Move `area` to `targetId` (a cluster id, or `UNSORTED_ID`). Works from any
   * source — cluster or Unsorted — since it first strips the area from every
   * cluster, then adds it to the target (a no-op add for Unsorted). Blocked when
   * the target cluster is already at the per-cluster cap. */
  function handleMoveArea(area: string, targetId: string) {
    if (targetId !== UNSORTED_ID) {
      const target = sanitized.find((cluster) => cluster.id === targetId);
      const alreadyThere = target?.areas.includes(area);
      if (target && !alreadyThere && isClusterFull(target)) {
        setError(clusterFullMessage);
        return;
      }
    }
    setError(null);
    let next = sanitized.map((cluster) => ({
      ...cluster,
      areas: cluster.areas.filter((a) => a !== area),
    }));
    if (targetId !== UNSORTED_ID) {
      next = next.map((cluster) =>
        cluster.id === targetId ? { ...cluster, areas: [...cluster.areas, area] } : cluster,
      );
    }
    emit(next);
  }

  const areaExists = (text: string, except?: string) =>
    areas.some(
      (a) => a !== except && a.toLowerCase() === text.toLowerCase(),
    );

  /** Add a brand-new interest to the declared areas and place it in `clusterId`
   * (or leave it in Unsorted). A no-op without `onAreasChange`. If the text
   * already exists it is just moved to the target. */
  function handleAddArea(clusterId: string, raw: string) {
    if (!onAreasChange) return;
    const text = raw.replace(/\s+/g, " ").trim();
    if (!text) return;
    if (clusterId !== UNSORTED_ID) {
      const target = sanitized.find((cluster) => cluster.id === clusterId);
      const alreadyThere = target?.areas.some(
        (a) => a.toLowerCase() === text.toLowerCase(),
      );
      if (target && !alreadyThere && isClusterFull(target)) {
        setError(clusterFullMessage);
        return;
      }
    }
    setError(null);
    const nextAreas = areaExists(text) ? areas : [...areas, text];
    let nextClusters = sanitized.map((cluster) => ({
      ...cluster,
      areas: cluster.areas.filter((a) => a.toLowerCase() !== text.toLowerCase()),
    }));
    if (clusterId !== UNSORTED_ID) {
      nextClusters = nextClusters.map((cluster) =>
        cluster.id === clusterId
          ? { ...cluster, areas: [...cluster.areas, text] }
          : cluster,
      );
    }
    onAreasChange(nextAreas);
    onChange(sanitizeClusters(nextClusters, nextAreas));
  }

  /** Remove an interest entirely — from the declared areas and any cluster. */
  function handleDeleteArea(area: string) {
    if (!onAreasChange) return;
    const nextAreas = areas.filter((a) => a !== area);
    const nextClusters = sanitized.map((cluster) => ({
      ...cluster,
      areas: cluster.areas.filter((a) => a !== area),
    }));
    onAreasChange(nextAreas);
    onChange(nextClusters);
  }

  /** Rename an interest everywhere it appears (declared areas + its cluster).
   * Ignored when the new text is blank or collides with a different area. */
  function handleRenameArea(oldArea: string, raw: string) {
    if (!onAreasChange) return;
    const text = raw.replace(/\s+/g, " ").trim();
    if (!text || text === oldArea || areaExists(text, oldArea)) return;
    const nextAreas = areas.map((a) => (a === oldArea ? text : a));
    const nextClusters = sanitized.map((cluster) => ({
      ...cluster,
      areas: cluster.areas.map((a) => (a === oldArea ? text : a)),
    }));
    onAreasChange(nextAreas);
    onChange(sanitizeClusters(nextClusters, nextAreas));
  }

  /** Move every area from `sourceId` into `targetId` and drop the (now empty)
   * source. The target keeps its own id and label. */
  function handleMergeInto(sourceId: string, targetId: string) {
    if (sourceId === targetId) {
      return;
    }
    const source = sanitized.find((cluster) => cluster.id === sourceId);
    if (!source) {
      return;
    }
    const target = sanitized.find((cluster) => cluster.id === targetId);
    if (
      target &&
      hasPerClusterLimit &&
      target.areas.length + source.areas.length > perClusterLimit
    ) {
      setError(
        `That merge would exceed the ${perClusterLimit}-topic limit per cluster on your plan.`,
      );
      return;
    }
    setError(null);
    const next = sanitized
      .filter((cluster) => cluster.id !== sourceId)
      .map((cluster) =>
        cluster.id === targetId
          ? { ...cluster, areas: [...cluster.areas, ...source.areas] }
          : cluster,
      );
    emit(next);
  }

  /** Split `area` out of its current cluster into a brand-new singleton cluster. */
  function handleSplitArea(area: string) {
    if (sanitized.length >= clusterLimit) {
      return;
    }
    const id = makeClusterId(area, sanitized.map((cluster) => cluster.id));
    const next = sanitized
      .map((cluster) => ({ ...cluster, areas: cluster.areas.filter((a) => a !== area) }))
      .concat([{ id, label: area, areas: [area] }]);
    emit(next);
  }

  function handleDropOn(targetId: string) {
    return (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragOverId(null);
      const raw = event.dataTransfer.getData("text/plain");
      if (!raw) {
        return;
      }
      try {
        const payload = JSON.parse(raw) as { area?: string };
        if (payload.area) {
          handleMoveArea(payload.area, targetId);
        }
      } catch {
        // Ignore malformed/foreign drag payloads.
      }
    };
  }

  async function handlePropose() {
    setError(null);
    setBusy("propose");
    try {
      const result = await proposeClusters({ areas, keywords, statement });
      onChange(
        sanitizeClusters(
          clampClustersToCaps(result.clusters, {
            maxClusters: clusterLimit,
            maxTopicsPerCluster: perClusterLimit,
          }),
          areas,
        ),
      );
      onWatchSeed?.(result.watch_topics);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not organize your interests. Try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleSortUnsorted() {
    setError(null);
    setBusy("sort");
    try {
      const result = await proposeClusters({ clusters: sanitized, unsorted });
      onChange(
        sanitizeClusters(
          clampClustersToCaps(result.clusters, {
            maxClusters: clusterLimit,
            maxTopicsPerCluster: perClusterLimit,
          }),
          areas,
        ),
      );
      onWatchSeed?.(result.watch_topics);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not sort your unsorted interests. Try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  if (areas.length === 0) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm text-[var(--text-secondary)]">
          Add a few research areas first — Mylo can group them into clusters once
          you have some.
        </p>
      </Card>
    );
  }

  const canCreateMore = sanitized.length < clusterLimit;
  // Show the plan-limit banner only when a tier cap was actually passed in — the
  // profile-edit / unrestricted usage keeps just the structural cluster ceiling.
  const showPlanLimits =
    maxClusters !== undefined || maxTopicsPerCluster !== undefined;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-serif text-lg font-semibold text-[var(--text-primary)]">
            Organize your interests
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            Group your research areas into a few named clusters, or let Mylo
            suggest a grouping. You&rsquo;re in full control — rename, delete, or
            add clusters and move areas between them.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handlePropose}
          disabled={busy !== null || areas.length < 2}
        >
          {busy === "propose" ? "Organizing…" : "Organize with Mylo"}
        </Button>
      </div>

      {showPlanLimits ? (
        <div
          role="note"
          className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-[var(--text-secondary)]"
        >
          <span className="font-semibold text-[var(--text-primary)]">
            Your plan:
          </span>
          <span>
            up to <strong>{clusterLimit}</strong>{" "}
            {clusterLimit === 1 ? "cluster" : "clusters"}
            {hasPerClusterLimit ? (
              <>
                , with <strong>{perClusterLimit}</strong>{" "}
                {perClusterLimit === 1 ? "topic" : "topics"} in each
              </>
            ) : null}
            . Mylo runs one search per cluster — upgrade to add more.
          </span>
          <span className="text-[var(--text-muted)]">
            ({sanitized.length}/{clusterLimit} clusters used)
          </span>
        </div>
      ) : null}

      {/* A high-level explanation of what clusters do, with a concrete example. */}
      <div className="rounded-xl border border-dashed border-border bg-[var(--surface-alt)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
        <p>
          <span className="font-semibold text-[var(--text-primary)]">
            Why clusters?
          </span>{" "}
          Mylo searches for each cluster on its own, so grouping your areas by
          theme gives you sharper, more diverse results — every recommendation is
          labeled with the cluster it matched, and a strong match in one cluster
          never crowds out the best of another.
        </p>
        <p className="mt-2">
          <span className="font-semibold text-[var(--text-primary)]">
            For example:
          </span>{" "}
          keeping <em>Medical AI Agents</em> and{" "}
          <em>Oceanography &amp; Data Assimilation</em> as separate clusters means
          Mylo hunts each topic distinctly and still surfaces the top ocean paper
          alongside your medical ones — instead of blending both into one search
          where the larger topic drowns out the other.
        </p>
      </div>

      {error ? (
        <p
          role="status"
          className="rounded-md border border-dashed border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        >
          {error}
        </p>
      ) : null}

      {areas.length === 1 ? (
        <p className="text-xs text-[var(--text-muted)]">
          Only one interest area so far — add more to start grouping them into
          clusters.
        </p>
      ) : null}

      {/* One cluster per row — a clear, full-width card each. */}
      <div className="space-y-3">
        {sanitized.map((cluster) => (
          <ClusterCard
            key={cluster.id}
            cluster={cluster}
            capacity={hasPerClusterLimit ? perClusterLimit : null}
            // A full cluster can't be a move/merge destination — leave it out of
            // the menus so the limit is felt as "no longer offered", not a error.
            mergeTargets={sanitized
              .filter((other) => other.id !== cluster.id && !isClusterFull(other))
              .map((other) => ({ key: other.id, label: other.label || "Untitled cluster" }))}
            moveTargetsFor={(area) => [
              ...sanitized
                .filter(
                  (other) =>
                    other.id !== cluster.id &&
                    (other.areas.includes(area) || !isClusterFull(other)),
                )
                .map((other) => ({ key: other.id, label: other.label || "Untitled cluster" })),
              { key: UNSORTED_ID, label: "Unsorted" },
              ...(canCreateMore
                ? [{ key: "__split__", label: `Split "${area}" into a new cluster` }]
                : []),
            ]}
            isDragOver={dragOverId === cluster.id}
            onRename={(label) => handleRename(cluster.id, label)}
            onDelete={() => handleDelete(cluster.id)}
            onMergeInto={(targetId) => handleMergeInto(cluster.id, targetId)}
            onDragOverCard={() => setDragOverId(cluster.id)}
            onDragLeaveCard={() =>
              setDragOverId((current) => (current === cluster.id ? null : current))
            }
            onDrop={handleDropOn(cluster.id)}
            onMoveArea={handleMoveArea}
            onSplitArea={handleSplitArea}
            canEditAreas={canEditAreas}
            onAddArea={(text) => handleAddArea(cluster.id, text)}
            onRenameArea={handleRenameArea}
            onDeleteArea={handleDeleteArea}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={handleCreate}
        disabled={!canCreateMore}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-3 text-sm font-medium text-[var(--text-secondary)] transition hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border disabled:hover:text-[var(--text-secondary)] motion-reduce:transition-none"
      >
        <span aria-hidden="true" className="text-lg leading-none">
          +
        </span>
        {canCreateMore
          ? "Add a cluster"
          : `Cluster limit reached (max ${clusterLimit})`}
      </button>

      <Card
        onDragOver={(event) => {
          event.preventDefault();
          setDragOverId(UNSORTED_ID);
        }}
        onDragLeave={() =>
          setDragOverId((current) => (current === UNSORTED_ID ? null : current))
        }
        onDrop={handleDropOn(UNSORTED_ID)}
        className={cn(
          "p-4 transition-colors motion-reduce:transition-none",
          dragOverId === UNSORTED_ID && "border-primary",
        )}
      >
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            Unsorted{" "}
            <span className="font-normal text-[var(--text-muted)]">
              ({unsorted.length})
            </span>
          </h4>
          {unsorted.length > 0 && sanitized.length > 0 ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleSortUnsorted}
              disabled={busy !== null}
            >
              {busy === "sort" ? "Sorting…" : "Sort unsorted with Mylo"}
            </Button>
          ) : null}
        </div>
        {unsorted.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">
            Everything is sorted into a cluster.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {unsorted.map((area) => (
              <AreaChip
                key={area}
                area={area}
                moveTargets={sanitized.map((cluster) => ({
                  key: cluster.id,
                  label: cluster.label || "Untitled cluster",
                }))}
                onMove={(targetId) => handleMoveArea(area, targetId)}
                canEdit={canEditAreas}
                onRename={(text) => handleRenameArea(area, text)}
                onDelete={() => handleDeleteArea(area)}
              />
            ))}
          </div>
        )}
        {canEditAreas ? (
          <div className="mt-3">
            <AddInterest
              placeholder="Add an interest (unsorted)…"
              onAdd={(text) => handleAddArea(UNSORTED_ID, text)}
            />
          </div>
        ) : null}
      </Card>
    </div>
  );
}

type ClusterCardProps = {
  cluster: ClusterGroup;
  /** Per-cluster interest cap (tier limit), or null when uncapped. */
  capacity: number | null;
  mergeTargets: MenuItem[];
  moveTargetsFor: (area: string) => MenuItem[];
  isDragOver: boolean;
  onRename: (label: string) => void;
  onDelete: () => void;
  onMergeInto: (targetId: string) => void;
  onDragOverCard: () => void;
  onDragLeaveCard: () => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onMoveArea: (area: string, targetId: string) => void;
  onSplitArea: (area: string) => void;
  canEditAreas: boolean;
  onAddArea: (text: string) => void;
  onRenameArea: (oldArea: string, text: string) => void;
  onDeleteArea: (area: string) => void;
};

function ClusterCard({
  cluster,
  capacity,
  mergeTargets,
  moveTargetsFor,
  isDragOver,
  onRename,
  onDelete,
  onMergeInto,
  onDragOverCard,
  onDragLeaveCard,
  onDrop,
  onMoveArea,
  onSplitArea,
  canEditAreas,
  onAddArea,
  onRenameArea,
  onDeleteArea,
}: ClusterCardProps) {
  const token = clusterAccentVar(cluster.id);
  const isFull = capacity !== null && cluster.areas.length >= capacity;

  return (
    <Card
      onDragOver={(event) => {
        event.preventDefault();
        onDragOverCard();
      }}
      onDragLeave={onDragLeaveCard}
      onDrop={onDrop}
      className={cn(
        "flex flex-col gap-3 p-4 transition-colors motion-reduce:transition-none",
        isDragOver && "border-2",
      )}
      style={{
        borderColor: isDragOver ? `var(${token})` : undefined,
      }}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: `var(${token})` }}
        />
        <input
          value={cluster.label}
          onChange={(event) => onRename(event.target.value)}
          placeholder="Name this cluster"
          aria-label="Cluster name"
          className="min-w-0 flex-1 rounded-md border border-border bg-[var(--surface-alt)] px-2 py-1 text-sm font-semibold text-[var(--text-primary)] outline-none transition focus-visible:border-input focus-visible:bg-[var(--surface)] focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
        />
        <span
          className={cn(
            "shrink-0 text-xs",
            isFull ? "font-semibold text-primary" : "text-[var(--text-muted)]",
          )}
          title={capacity !== null ? `${cluster.areas.length} of ${capacity} topics` : undefined}
        >
          {capacity !== null
            ? `${cluster.areas.length}/${capacity}`
            : cluster.areas.length}
        </span>
        <InlineMenu
          trigger="Merge into"
          triggerAriaLabel={`Merge "${cluster.label}" into another cluster`}
          triggerClassName="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-surface-alt hover:text-foreground"
          items={mergeTargets}
          onSelect={onMergeInto}
          align="right"
        />
        <button
          type="button"
          onClick={onDelete}
          aria-label={`Delete "${cluster.label}"`}
          title="Delete cluster (its areas return to Unsorted)"
          className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-[var(--text-muted)] transition hover:bg-destructive/10 hover:text-destructive motion-reduce:transition-none"
        >
          Delete
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {cluster.areas.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">
            {canEditAreas
              ? "No interests here yet — add one below, or drop / move one in."
              : "Drop an area here, or use its “Move” menu."}
          </p>
        ) : (
          cluster.areas.map((area) => (
            <AreaChip
              key={area}
              area={area}
              moveTargets={moveTargetsFor(area)}
              onMove={(targetId) => {
                if (targetId === "__split__") {
                  onSplitArea(area);
                } else {
                  onMoveArea(area, targetId);
                }
              }}
              canEdit={canEditAreas}
              onRename={(text) => onRenameArea(area, text)}
              onDelete={() => onDeleteArea(area)}
            />
          ))
        )}
      </div>

      {canEditAreas ? (
        isFull ? (
          <p className="text-xs text-[var(--text-muted)]">
            This cluster is full ({capacity}/{capacity}). Remove a topic to add
            another, or start a new cluster.
          </p>
        ) : (
          <AddInterest
            placeholder="Add an interest to this cluster…"
            onAdd={onAddArea}
          />
        )
      ) : null}
    </Card>
  );
}

type AreaChipProps = {
  area: string;
  moveTargets: MenuItem[];
  onMove: (targetId: string) => void;
  canEdit?: boolean;
  onRename?: (text: string) => void;
  onDelete?: () => void;
};

function AreaChip({ area, moveTargets, onMove, canEdit, onRename, onDelete }: AreaChipProps) {
  // Local draft so typing doesn't re-key the list on every keystroke; the parent
  // keys each chip by its area string, so a committed rename remounts this chip
  // fresh with the new value — no effect needed to resync.
  const [draft, setDraft] = useState(area);

  function commit() {
    const text = draft.trim();
    if (text && text !== area) {
      onRename?.(text);
    } else if (!text) {
      setDraft(area); // an emptied field reverts rather than deletes
    }
  }

  // Read-only usage (no area editing wired): a plain draggable chip + move menu.
  if (!canEdit) {
    return (
      <span
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData("text/plain", JSON.stringify({ area }));
          event.dataTransfer.effectAllowed = "move";
        }}
        className="inline-flex cursor-grab items-center gap-1 rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] active:cursor-grabbing"
      >
        {area}
        <InlineMenu
          trigger={<span aria-hidden="true" className="text-[10px] leading-none">▾</span>}
          triggerAriaLabel={`Move "${area}"`}
          triggerClassName="rounded-full p-0.5 text-[var(--text-muted)] hover:bg-surface-alt hover:text-foreground"
          items={moveTargets}
          onSelect={onMove}
        />
      </span>
    );
  }

  // Editable interest: the name is a text field you type straight into (commits
  // on blur / Enter), with a drag handle to move it and a remove button. No
  // separate "edit" toggle — the field is always live.
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-card py-1 pl-1.5 pr-1.5 text-xs font-medium text-[var(--text-primary)]">
      <span
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData("text/plain", JSON.stringify({ area }));
          event.dataTransfer.effectAllowed = "move";
        }}
        title="Drag to another cluster"
        aria-label={`Drag "${area}" to another cluster`}
        className="cursor-grab select-none px-0.5 text-[var(--text-muted)] hover:text-foreground active:cursor-grabbing"
      >
        ⠿
      </span>
      <input
        value={draft}
        aria-label={`Interest name (${area})`}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.blur();
          } else if (event.key === "Escape") {
            setDraft(area);
            event.currentTarget.blur();
          }
        }}
        size={Math.max(draft.length, 6)}
        className="min-w-0 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-xs font-medium text-[var(--text-primary)] outline-none transition hover:border-border focus-visible:border-input focus-visible:bg-[var(--surface-alt)] focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
      />
      <InlineMenu
        trigger={<span aria-hidden="true" className="text-[10px] leading-none">▾</span>}
        triggerAriaLabel={`Move "${area}"`}
        triggerClassName="rounded-full p-0.5 text-[var(--text-muted)] hover:bg-surface-alt hover:text-foreground"
        items={moveTargets}
        onSelect={onMove}
      />
      <button
        type="button"
        onClick={onDelete}
        aria-label={`Remove "${area}"`}
        title="Remove interest"
        className="rounded-full px-1 leading-none text-[var(--text-muted)] hover:text-destructive"
      >
        <span aria-hidden="true" className="text-sm">×</span>
      </button>
    </span>
  );
}

type AddInterestProps = {
  onAdd: (text: string) => void;
  placeholder?: string;
};

/** A small inline "add an interest" input — Enter or the Add button commits and
 * clears. Not a `<form>` (the organizer may render inside another form), so it
 * commits on Enter/click instead of submit. */
function AddInterest({ onAdd, placeholder }: AddInterestProps) {
  const [value, setValue] = useState("");

  function commit() {
    const text = value.trim();
    if (!text) return;
    onAdd(text);
    setValue("");
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
          }
        }}
        placeholder={placeholder ?? "Add an interest…"}
        aria-label={placeholder ?? "Add an interest"}
        className="min-w-0 flex-1 rounded-md border border-border bg-[var(--surface-alt)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none transition focus-visible:border-input focus-visible:bg-[var(--surface)] focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={commit}
        disabled={value.trim() === ""}
      >
        Add
      </Button>
    </div>
  );
}

type InlineMenuProps = {
  trigger: React.ReactNode;
  triggerAriaLabel: string;
  triggerClassName?: string;
  items: MenuItem[];
  onSelect: (key: string) => void;
  align?: "left" | "right";
};

/**
 * A small, keyboard-usable dropdown ("Move to ▾", "Merge into ▾") built from
 * plain state rather than a menu library — closes on outside click and Escape,
 * and every item is a real `<button role="menuitem">` so it works without a
 * pointer. Renders nothing when there is nowhere to move/merge to.
 */
function InlineMenu({
  trigger,
  triggerAriaLabel,
  triggerClassName,
  items,
  onSelect,
  align = "left",
}: InlineMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (items.length === 0) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={triggerAriaLabel}
        onClick={() => setOpen((value) => !value)}
        className={cn("focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", triggerClassName)}
      >
        {trigger}
      </button>
      {open ? (
        <div
          role="menu"
          aria-label={triggerAriaLabel}
          className={cn(
            "absolute z-20 mt-1 min-w-44 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-[var(--shadow)]",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onSelect(item.key);
              }}
              className="block w-full px-3 py-2 text-left text-sm text-[var(--text-primary)] hover:bg-surface-alt focus-visible:bg-surface-alt focus-visible:outline-none"
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
