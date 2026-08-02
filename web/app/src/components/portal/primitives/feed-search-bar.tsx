"use client";

import * as React from "react";

import { SearchIcon } from "@/components/portal/icons";
import { clusterAccentVar, type ClusterRef } from "@/components/portal/primitives/cluster-badge";

/**
 * The keyword search + cluster chip row that sits above a recommendation feed.
 *
 * Research Papers introduced this pattern — one text field that narrows the
 * already-fetched feed, and one line of cluster chips so a reader can pin the
 * page to a single research theme. Grants, Fellowships and Conferences now use
 * the same control, so the four feeds read as one product rather than four
 * pages that each invented their own top-of-page filter.
 *
 * Everything here is presentational: the caller owns `query`/`selectedCluster`
 * state and does the actual filtering, since each feed searches its own fields.
 */

/**
 * The distinct clusters present across a feed, in the order they first appear —
 * the source of the cluster chip row. A profile whose items carry no cluster at
 * all yields an empty list and the caller hides the row.
 */
export function clusterOptions(
  items: { cluster?: ClusterRef | null }[],
): ClusterRef[] {
  const seen = new Map<string, string>();
  for (const item of items) {
    if (item.cluster && !seen.has(item.cluster.id)) {
      seen.set(item.cluster.id, item.cluster.label);
    }
  }
  return Array.from(seen, ([id, label]) => ({ id, label }));
}

/** Case-insensitive substring test across an item's searchable text fields. */
export function matchesQuery(haystacks: (string | undefined)[], needle: string): boolean {
  if (!needle) return true;
  const q = needle.toLowerCase();
  return haystacks.some((text) => (text ?? "").toLowerCase().includes(q));
}

export function FeedSearchBar({
  query,
  onQueryChange,
  placeholder,
  clusters,
  selectedCluster,
  onClusterChange,
  className,
}: {
  query: string;
  onQueryChange: (next: string) => void;
  /** Doubles as the field's accessible name (rendered screen-reader only). */
  placeholder: string;
  clusters: ClusterRef[];
  selectedCluster: string | null;
  onClusterChange: (next: string | null) => void;
  className?: string;
}) {
  /** Selecting a cluster narrows the feed to it; re-selecting clears. */
  const toggleCluster = (clusterId: string) => {
    onClusterChange(selectedCluster === clusterId ? null : clusterId);
  };

  return (
    <div className={className ?? "mb-5 space-y-3"}>
      <label className="relative block">
        <span className="sr-only">{placeholder}</span>
        <SearchIcon
          size={16}
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)]"
        />
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-full border border-[var(--border)] bg-[var(--surface)] py-2 pl-9 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[color-mix(in_srgb,var(--primary)_45%,var(--border))] focus:outline-none"
        />
      </label>

      {/* Clusters, and only clusters — the rail stays one line: pick a theme,
          or see everything. */}
      {clusters.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
            Clusters
          </span>
          <button
            type="button"
            onClick={() => onClusterChange(null)}
            aria-pressed={selectedCluster === null}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              selectedCluster === null
                ? "border-[color-mix(in_srgb,var(--primary)_45%,transparent)] bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] text-primary"
                : "border-[var(--border)] bg-[var(--surface-alt)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            All
          </button>
          {clusters.map((cluster) => {
            const on = selectedCluster === cluster.id;
            const token = clusterAccentVar(cluster.id);
            return (
              <button
                key={cluster.id}
                type="button"
                onClick={() => toggleCluster(cluster.id)}
                aria-pressed={on}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors"
                style={
                  on
                    ? {
                        borderColor: `color-mix(in srgb, var(${token}) 45%, transparent)`,
                        backgroundColor: `color-mix(in srgb, var(${token}) 14%, transparent)`,
                        color: `var(${token})`,
                      }
                    : {
                        borderColor: "var(--border)",
                        backgroundColor: "var(--surface-alt)",
                        color: "var(--text-secondary)",
                      }
                }
              >
                <span
                  aria-hidden="true"
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: `var(${token})` }}
                />
                {cluster.label}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
