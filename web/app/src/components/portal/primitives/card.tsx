import * as React from "react";

import { cn } from "@/lib/utils";

type CardProps = React.HTMLAttributes<HTMLDivElement> & {
  /** A left primary rule (Mylo summary) or a full gold border (opportunities). */
  accent?: "primary-rule" | "gold";
};

/**
 * The dashboard's soft surface panel: rounded, thin-bordered, warm-shadowed.
 * The base building block every section card composes (style guide: soft panels,
 * rounded cards, thin borders, warm shadows).
 */
export function Card({ className, accent, ...props }: CardProps) {
  return (
    <div
      className={cn(
        // `relative` so a card-scoped overlay (the undo popup a feed card
        // raises after Ignore / Reminder / Bookmark) centres on the card
        // itself, wherever inside it the control that raised it happens to sit.
        "relative rounded-2xl border border-border bg-surface shadow-[var(--shadow)]",
        accent === "primary-rule" && "border-l-4 border-l-primary",
        accent === "gold" && "border-accent",
        className,
      )}
      {...props}
    />
  );
}
