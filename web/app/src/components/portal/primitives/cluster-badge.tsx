import * as React from "react";

import { cn } from "@/lib/utils";

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
export function ClusterBadge({
  cluster,
  className,
}: {
  cluster: ClusterRef;
  className?: string;
}) {
  const token = clusterAccentVar(cluster.id);
  return (
    <span
      className={cn(
        // Shrinkable, not fixed: on a phone the card is narrower than a long
        // theme label, and a badge that refuses to shrink runs off the card
        // edge instead of clipping its own text.
        "inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1",
        className,
      )}
      title={cluster.label}
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
      <span className="min-w-0 truncate text-xs font-semibold leading-none text-[var(--text-primary)]">
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
  // A cluster whose label did not resolve has nothing to say — naming it would
  // print "Also: , " and read as a rendering fault rather than as a theme.
  const named = (clusters ?? []).filter((c) => c && c.label);
  if (named.length === 0) return null;
  const shown = named.slice(0, MAX_BRIDGE_LABELS);
  const more = named.length - shown.length;
  const label = `Also: ${shown.map((c) => c.label).join(", ")}${
    more > 0 ? `, +${more} more` : ""
  }`;
  return (
    <span
      className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-dashed border-[var(--border)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]"
      title={named.map((c) => c.label).join(", ")}
    >
      {/* Two theme names run past the width of a phone-sized card, so the label
          clips inside its own pill rather than pushing the pill off the card. */}
      <span className="min-w-0 truncate">{label}</span>
    </span>
  );
}

/**
 * The badge row a card carries beneath its title: the attributed theme, then the
 * others it bridges into.
 *
 * These used to stack vertically inside the match rail, which made the rail as
 * wide as the longest theme label and squeezed the title column on every card in
 * the feed to pay for it. Horizontally, under the title, they cost one row of
 * height that wraps when it has to, and they sit beside the deadline control
 * rather than above it — the arrangement the Research Papers card already used.
 *
 * Returns null when the item carries no themes, so callers can render it
 * unconditionally without guarding first.
 */
export function ClusterRow({
  cluster,
  bridgeClusters,
  leading,
  className,
}: {
  cluster?: ClusterRef | null;
  bridgeClusters?: ClusterRef[] | null;
  /**
   * Tags that qualify the match rather than name a theme — "New", "Updated".
   * They share this row because they are the same size and the same kind of
   * aside, and because a row of their own would cost every card the height
   * whether or not it had one. Passed as a node so this primitive does not have
   * to import from the sections that own those tags.
   */
  leading?: React.ReactNode;
  className?: string;
}) {
  // The primary badge already names the attributed theme, so a bridge list that
  // repeats it would print the same label twice on one row.
  const bridges = (bridgeClusters ?? []).filter(
    (c) => c && c.label && c.id !== cluster?.id,
  );
  if (!leading && !cluster && bridges.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {leading}
      {cluster ? <ClusterBadge cluster={cluster} /> : null}
      <BridgeBadge clusters={bridges} />
    </div>
  );
}
