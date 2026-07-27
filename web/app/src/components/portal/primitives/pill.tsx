import * as React from "react";

import { cn } from "@/lib/utils";

export type PillTone =
  | "primary"
  | "accent"
  | "neutral"
  | "clay"
  | "review"
  | "dashed";

const TONE: Record<PillTone, string> = {
  // On track / active
  primary: "bg-[color-mix(in_srgb,var(--primary)_14%,transparent)] text-primary",
  // Opportunity / fit signal (gold)
  accent: "bg-brand-accent-soft text-[color-mix(in_srgb,var(--accent)_75%,var(--text-primary))]",
  // Planning / generic
  neutral: "bg-surface-alt text-[var(--text-secondary)]",
  // Urgency / deadline (terracotta)
  clay: "bg-clay-soft text-clay",
  // Needs review (warm gold-soft)
  review: "bg-brand-accent-soft text-[color-mix(in_srgb,var(--accent)_75%,var(--text-primary))]",
  // Soon / coming
  dashed: "border border-dashed border-border text-[var(--text-secondary)]",
};

type PillProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: PillTone;
};

/** A small status/badge chip. Color is never the only signal — always has text. */
export function Pill({ tone = "neutral", className, ...props }: PillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
        TONE[tone],
        className,
      )}
      {...props}
    />
  );
}
