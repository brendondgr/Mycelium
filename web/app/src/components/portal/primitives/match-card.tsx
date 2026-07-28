import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { cn } from "@/lib/utils";

type MatchCardProps = {
  /** The `MatchRing` for this item, or null when there is no percent to show. */
  ring?: React.ReactNode;
  /** Badges, title and the item's own meta line — the block beside the ring. */
  head: React.ReactNode;
  /** Description, reason, chips, link — everything that runs full width. */
  children?: React.ReactNode;
  className?: string;
};

/**
 * The shape every scored feed card shares: the match ring in a notch at the
 * top-left, the head beside it, and the body reclaiming the full width beneath.
 *
 * The ring used to sit in a flex column running the whole height of the card,
 * which left a tall empty margin down the left of anything with a real abstract
 * — the taller the card, the worse it looked. Here the gutter is one grid row
 * tall: only the head is indented past the ring, and the description, reason
 * and link start back at the card's left edge.
 *
 * With no ring (the cross-embedding tail has no percent) the gutter is not
 * rendered at all, so nothing is indented past empty space.
 */
export function MatchCard({ ring, head, children, className }: MatchCardProps) {
  const cardClass = cn(
    "p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0",
    className,
  );

  if (!ring) {
    return (
      <Card className={cardClass}>
        {head}
        {children}
      </Card>
    );
  }

  return (
    <Card className={cardClass}>
      <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 sm:gap-x-5">
        <div className="col-start-1 row-start-1 self-start">{ring}</div>
        <div className="col-start-2 row-start-1 min-w-0">{head}</div>
        {children ? (
          <div className="col-span-2 min-w-0">{children}</div>
        ) : null}
      </div>
    </Card>
  );
}
