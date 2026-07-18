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
};

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
}: ClusterOrganizerProps) {
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

  function handleRename(id: string, label: string) {
    emit(sanitized.map((cluster) => (cluster.id === id ? { ...cluster, label } : cluster)));
  }

  function handleCreate() {
    if (sanitized.length >= MAX_CLUSTERS) {
      return;
    }
    const id = makeClusterId("New cluster", sanitized.map((cluster) => cluster.id));
    emit([...sanitized, { id, label: "New cluster", areas: [] }]);
  }

  function handleDelete(id: string) {
    const target = sanitized.find((cluster) => cluster.id === id);
    if (!target || target.areas.length > 0) {
      return;
    }
    emit(sanitized.filter((cluster) => cluster.id !== id));
  }

  /** Move `area` to `targetId` (a cluster id, or `UNSORTED_ID`). Works from any
   * source — cluster or Unsorted — since it first strips the area from every
   * cluster, then adds it to the target (a no-op add for Unsorted). */
  function handleMoveArea(area: string, targetId: string) {
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
    if (sanitized.length >= MAX_CLUSTERS) {
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
      onChange(sanitizeClusters(result.clusters, areas));
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
      onChange(sanitizeClusters(result.clusters, areas));
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

  const canCreateMore = sanitized.length < MAX_CLUSTERS;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-serif text-lg font-semibold text-[var(--text-primary)]">
            Organize your interests
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            Group your research areas into a few named clusters, or let Mylo
            suggest a grouping.
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {sanitized.map((cluster) => (
          <ClusterCard
            key={cluster.id}
            cluster={cluster}
            mergeTargets={sanitized
              .filter((other) => other.id !== cluster.id)
              .map((other) => ({ key: other.id, label: other.label || "Untitled cluster" }))}
            moveTargetsFor={(area) => [
              ...sanitized
                .filter((other) => other.id !== cluster.id)
                .map((other) => ({ key: other.id, label: other.label || "Untitled cluster" })),
              { key: UNSORTED_ID, label: "Unsorted" },
              ...(canCreateMore
                ? [{ key: "__split__", label: `Split "${area}" into a new cluster` }]
                : []),
            ]}
            canDelete={cluster.areas.length === 0}
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
          />
        ))}

        <button
          type="button"
          onClick={handleCreate}
          disabled={!canCreateMore}
          className="flex min-h-[96px] flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-border p-4 text-sm font-medium text-[var(--text-secondary)] transition hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border disabled:hover:text-[var(--text-secondary)] motion-reduce:transition-none"
        >
          <span aria-hidden="true" className="text-lg leading-none">
            +
          </span>
          {canCreateMore ? "New cluster" : "Cluster limit reached (6)"}
        </button>
      </div>

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
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

type ClusterCardProps = {
  cluster: ClusterGroup;
  mergeTargets: MenuItem[];
  moveTargetsFor: (area: string) => MenuItem[];
  canDelete: boolean;
  isDragOver: boolean;
  onRename: (label: string) => void;
  onDelete: () => void;
  onMergeInto: (targetId: string) => void;
  onDragOverCard: () => void;
  onDragLeaveCard: () => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onMoveArea: (area: string, targetId: string) => void;
  onSplitArea: (area: string) => void;
};

function ClusterCard({
  cluster,
  mergeTargets,
  moveTargetsFor,
  canDelete,
  isDragOver,
  onRename,
  onDelete,
  onMergeInto,
  onDragOverCard,
  onDragLeaveCard,
  onDrop,
  onMoveArea,
  onSplitArea,
}: ClusterCardProps) {
  const token = clusterAccentVar(cluster.id);

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
          placeholder="Untitled cluster"
          aria-label="Cluster name"
          className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold text-[var(--text-primary)] outline-none transition hover:border-border focus-visible:border-input focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
        />
        <span className="shrink-0 text-xs text-[var(--text-muted)]">
          {cluster.areas.length}
        </span>
        <InlineMenu
          trigger="Merge into"
          triggerAriaLabel={`Merge "${cluster.label}" into another cluster`}
          triggerClassName="shrink-0 text-xs font-medium text-[var(--text-secondary)] hover:text-foreground"
          items={mergeTargets}
          onSelect={onMergeInto}
          align="right"
        />
        <button
          type="button"
          onClick={onDelete}
          disabled={!canDelete}
          aria-label={`Delete "${cluster.label}"`}
          title={canDelete ? "Delete cluster" : "Move its areas out first"}
          className="shrink-0 rounded-full px-1.5 py-0.5 text-sm text-[var(--text-muted)] transition hover:bg-destructive/10 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-[var(--text-muted)] motion-reduce:transition-none"
        >
          ×
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {cluster.areas.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">
            Drop an area here, or use its &ldquo;Move&rdquo; menu.
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
            />
          ))
        )}
      </div>
    </Card>
  );
}

type AreaChipProps = {
  area: string;
  moveTargets: MenuItem[];
  onMove: (targetId: string) => void;
};

function AreaChip({ area, moveTargets, onMove }: AreaChipProps) {
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
        trigger={
          <span aria-hidden="true" className="text-[10px] leading-none">
            ▾
          </span>
        }
        triggerAriaLabel={`Move "${area}"`}
        triggerClassName="rounded-full p-0.5 text-[var(--text-muted)] hover:bg-surface-alt hover:text-foreground"
        items={moveTargets}
        onSelect={onMove}
      />
    </span>
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
