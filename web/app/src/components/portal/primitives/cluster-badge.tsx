import * as React from "react";

/** The categorical cluster accent palette defined in `theme.css` (`--cluster-1`
 * … `--cluster-8`). */
const CLUSTER_TOKEN_COUNT = 8;

/**
 * A small, stable string hash (djb2) — deterministic across renders, page
 * loads, and days, so a given cluster id always lands on the same bucket.
 */
function hashString(input: string): number {
  let hash = 5381;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash * 33) ^ input.charCodeAt(i);
  }
  return hash >>> 0;
}

/**
 * Map a cluster id to one of the 8 categorical `--cluster-N` accent tokens
 * (`theme.css`). The same id always resolves to the same token, so a cluster's
 * color reads consistently everywhere it appears — the paper card badge, the
 * filter rail chip, and the compact dot on the Overview's Top Papers panel.
 * Returns the bare CSS custom property name (e.g. `"--cluster-3"`); callers
 * wrap it in `var(...)`.
 */
export function clusterAccentVar(id: string): string {
  const index = hashString(id) % CLUSTER_TOKEN_COUNT;
  return `--cluster-${index + 1}`;
}

export type ClusterRef = { id: string; label: string };

/**
 * The primary cluster badge: a filled dot in the cluster's stable accent color
 * plus its label, in a soft tinted pill — the same border/tint `color-mix`
 * treatment as the match ring, just keyed on the cluster's accent token
 * instead of a semantic fit color. Renders in the badge row at the top of a
 * card whenever the item carries an attributed `cluster`.
 */
export function ClusterBadge({ cluster }: { cluster: ClusterRef }) {
  const token = clusterAccentVar(cluster.id);
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
      style={{
        borderColor: `color-mix(in srgb, var(${token}) 35%, var(--border))`,
        backgroundColor: `color-mix(in srgb, var(${token}) 10%, var(--surface))`,
      }}
    >
      <span
        aria-hidden="true"
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: `var(${token})` }}
      />
      <span className="text-xs font-semibold leading-none text-[var(--text-primary)]">
        {cluster.label}
      </span>
    </span>
  );
}

/** How many bridge-cluster labels to name before collapsing to "+N more". */
const MAX_BRIDGE_LABELS = 2;

/**
 * A quieter, secondary badge naming the other clusters a paper also bridges
 * into ("Also relevant to …"). Dashed border, muted text — deliberately less
 * prominent than `ClusterBadge` since bridging is supplementary context, not
 * the paper's primary attribution. Returns null when there are no bridge
 * clusters so callers can render it unconditionally.
 */
export function BridgeBadge({ clusters }: { clusters: ClusterRef[] }) {
  if (!clusters || clusters.length === 0) return null;
  const shown = clusters.slice(0, MAX_BRIDGE_LABELS);
  const more = clusters.length - shown.length;
  const label = `Also: ${shown.map((c) => c.label).join(", ")}${
    more > 0 ? `, +${more} more` : ""
  }`;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-dashed border-[var(--border)] px-2.5 py-1 text-xs font-medium text-[var(--text-muted)]"
      title={clusters.map((c) => c.label).join(", ")}
    >
      {label}
    </span>
  );
}
