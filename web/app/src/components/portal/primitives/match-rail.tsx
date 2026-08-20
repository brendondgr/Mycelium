import * as React from "react";

import { ClusterBadge, type ClusterRef } from "@/components/portal/primitives/cluster-badge";
import { MatchRing } from "@/components/portal/primitives/match-ring";
import { NewTag, UpdatedTag } from "@/components/portal/sections/opportunity-bits";

/** How many of the reader's themes a card names before it stops listing them. */
export const MAX_RAIL_CLUSTERS = 3;

/**
 * The side panel every matched opportunity card carries: Mylo's recommendation
 * (the percent ring and its strength word), then — directly beneath it — the
 * "New" tag when this is a fresh retrieval, then the reader's matching clusters.
 *
 * The order is the point. The ring is the recommendation; "New" qualifies the
 * recommendation ("…and you haven't seen it"), so it belongs under the ring
 * rather than in the title block competing with the theme badges. The clusters
 * say which of the reader's research themes pulled the item in, and are capped
 * at {@link MAX_RAIL_CLUSTERS}: past three, a rail of badges stops reading as
 * attribution and starts reading as a tag cloud, and it would push the title
 * column narrower on every card in the feed.
 *
 * The rail is a fixed width so titles line up down the whole feed regardless of
 * how long any one cluster label happens to be; labels themselves truncate
 * rather than wrapping the rail wider.
 *
 * With no percent (the cross-embedding tail) the ring renders nothing, and the
 * rail still carries whatever tags the item has.
 */
export function MatchRail({
  percent,
  origin,
  scope,
  isNew = false,
  isUpdated = false,
  updatedReason,
  cluster,
  bridgeClusters = [],
}: {
  percent: number | null | undefined;
  origin?: "llm" | "fallback" | "rules";
  /** Whose profile the percent is measured against, when not the reader's. */
  scope?: string;
  isNew?: boolean;
  isUpdated?: boolean;
  updatedReason?: string;
  /** The attributed (primary) cluster, listed first. */
  cluster?: ClusterRef | null;
  /** The other themes the item also cleared, listed after the primary one. */
  bridgeClusters?: ClusterRef[];
}) {
  const clusters = React.useMemo(() => {
    const all = cluster ? [cluster, ...bridgeClusters] : bridgeClusters;
    const seen = new Set<string>();
    return all
      .filter((c) => {
        if (!c || seen.has(c.id)) return false;
        seen.add(c.id);
        return true;
      })
      .slice(0, MAX_RAIL_CLUSTERS);
  }, [cluster, bridgeClusters]);

  return (
    <div className="flex w-24 shrink-0 flex-col items-center gap-2 sm:w-28">
      <MatchRing percent={percent} origin={origin} scope={scope} />
      {isNew ? <NewTag /> : null}
      {isUpdated ? <UpdatedTag reason={updatedReason} /> : null}
      {clusters.length > 0 ? (
        <div className="flex w-full flex-col items-center gap-1.5">
          {clusters.map((c) => (
            <ClusterBadge key={c.id} cluster={c} className="max-w-full" />
          ))}
        </div>
      ) : null}
    </div>
  );
}
