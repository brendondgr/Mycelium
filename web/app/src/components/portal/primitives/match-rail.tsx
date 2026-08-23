import * as React from "react";

import { ClusterBadge, type ClusterRef } from "@/components/portal/primitives/cluster-badge";
import type { Verdict } from "@/lib/portal/types";
import { PositionMark, VerdictBadge } from "@/components/portal/primitives/verdict-badge";
import { NewTag, UpdatedTag } from "@/components/portal/sections/opportunity-bits";

/** How many of the reader's themes a card names before it stops listing them. */
export const MAX_RAIL_CLUSTERS = 3;

/**
 * The side panel every matched card carries: the item's place in its theme,
 * Mylo's verdict on it, then the "New" tag when this is a fresh retrieval, then
 * the reader's matching themes.
 *
 * The order is the point. Position and verdict are the recommendation; "New"
 * qualifies it ("…and you haven't seen it"), so it belongs beneath rather than in
 * the title block competing with the theme badges. The themes say which strand of
 * the reader's work pulled the item in, and are capped at
 * {@link MAX_RAIL_CLUSTERS}: past three, a rail of badges stops reading as
 * attribution and starts reading as a tag cloud, and it would push the title
 * column narrower on every card in the feed.
 *
 * The rail is a fixed width so titles line up down the whole feed regardless of
 * how long any one theme label happens to be; labels themselves truncate rather
 * than wrapping the rail wider.
 *
 * Where the percent ring used to sit, there is now a position and a chip. The
 * ring's number was a language model's guess at a similarity rendered beside a
 * real embedding cosine, with nothing to tell a reader which was which. An
 * unscored item shows neither, rather than being given a fake one.
 */
export function MatchRail({
  verdict,
  position,
  origin,
  scope,
  isNew = false,
  isUpdated = false,
  updatedReason,
  cluster,
  bridgeClusters = [],
}: {
  verdict?: Verdict | null;
  /** Place within the item's own theme's list — never a global rank. */
  position?: number | null;
  origin?: "llm" | "fallback" | "rules";
  /** Whose profile the judgement is about, when not the reader's. */
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
      <PositionMark position={position} theme={cluster?.label} />
      <VerdictBadge verdict={verdict} origin={origin} scope={scope} />
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
