import * as React from "react";

import type { Verdict } from "@/lib/portal/types";
import { PositionMark, VerdictBadge } from "@/components/portal/primitives/verdict-badge";
import { NewTag, UpdatedTag } from "@/components/portal/sections/opportunity-bits";

/**
 * The side panel every matched card carries: the item's place in its theme,
 * Mylo's verdict on it, then the "New" tag when this is a fresh retrieval.
 *
 * The order is the point. Position and verdict are the recommendation; "New"
 * qualifies it ("…and you haven't seen it"), so it belongs beneath rather than in
 * the title block competing with the title itself.
 *
 * The reader's matching themes used to stack vertically here, which set the
 * rail's width from the longest theme label and took the space out of the title
 * column on every card in the feed. They now run as a row under the title
 * (`ClusterRow`), where they wrap instead of pushing the layout around, and the
 * rail is back to a narrow fixed column so titles line up down the whole feed.
 *
 * Where the percent ring used to sit, there is now a position and a chip. The
 * ring's number was a language model's guess at a similarity rendered beside a
 * real embedding cosine, with nothing to tell a reader which was which. An
 * unscored item shows neither, rather than being given a fake one.
 */
export function MatchRail({
  verdict,
  position,
  positionOf,
  theme,
  origin,
  scope,
  isNew = false,
  isUpdated = false,
  updatedReason,
}: {
  verdict?: Verdict | null;
  /** Place within the item's own theme's list — never a global rank. */
  position?: number | null;
  /** That theme's slate length, when the row records it. */
  positionOf?: number | null;
  /** The theme the position is within — named in the mark's tooltip and label. */
  theme?: string;
  origin?: "llm" | "fallback" | "rules";
  /** Whose profile the judgement is about, when not the reader's. */
  scope?: string;
  isNew?: boolean;
  isUpdated?: boolean;
  updatedReason?: string;
}) {
  return (
    <div className="flex w-16 shrink-0 flex-col items-center gap-2">
      <PositionMark position={position} of={positionOf} theme={theme} />
      <VerdictBadge verdict={verdict} origin={origin} scope={scope} />
      {isNew ? <NewTag /> : null}
      {isUpdated ? <UpdatedTag reason={updatedReason} /> : null}
    </div>
  );
}
