import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { cn } from "@/lib/utils";

type MatchCardProps = {
  /** Title, meta lines, theme badges and the card's tools — the top block. */
  head: React.ReactNode;
  /** Description, reason, chips, link — everything beneath the head. */
  children?: React.ReactNode;
  className?: string;
};

/**
 * The shape every feed card shares: a soft panel with the head at the top and
 * the body beneath it, both starting at the card's left edge.
 *
 * There used to be a judgement gutter down the left — first a percent ring, then
 * a rail carrying a position and a verdict chip. Both are gone. The percent
 * implied a measurement nobody made; the position and the verdict that replaced
 * it were per-theme, and a feed that interleaves themes rendered them as a
 * column of repeated and apparently unsorted numbers. What is left is a card
 * whose content starts where the card does, with no reserved column standing
 * empty on the many rows that carried no judgement at all.
 */
export function MatchCard({ head, children, className }: MatchCardProps) {
  return (
    <Card
      className={cn(
        "p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        className,
      )}
    >
      {head}
      {children}
    </Card>
  );
}
