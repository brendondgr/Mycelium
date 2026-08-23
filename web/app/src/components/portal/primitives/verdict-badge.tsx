"use client";

import * as React from "react";

import type { Verdict } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * What each verdict says, in the reader's words. `skip` is here for completeness
 * but never renders as a chip — an item Mylo judged not worth reading keeps its
 * place in the list and its reference row, and spending a badge on it would spend
 * the reader's attention on the one judgement that says not to.
 */
export const VERDICT_LABEL: Record<Verdict, string> = {
  read: "Read",
  skim: "Skim",
  file: "File",
  skip: "Skip",
};

export const VERDICT_BLURB: Record<Verdict, string> = {
  read: "Worth your attention today.",
  skim: "Worth a look — the abstract may be enough.",
  file: "Relevant, but not urgent. Keep it for later.",
  skip: "Probably not worth your time.",
};

/**
 * The chip's colour, by verdict.
 *
 * Gold is deliberately absent: `docs/styles.md` reserves it for opportunity and
 * deadline signals, so a grant deadline never competes visually with a relevance
 * judgement sitting two centimetres away from it.
 */
const TONE: Record<Verdict, string> = {
  read: "bg-[var(--primary)] text-[var(--on-primary,#FFFDF8)] border-transparent",
  skim: "bg-[var(--secondary)] text-[var(--text-primary)] border-transparent",
  file: "bg-[var(--surface-alt)] text-[var(--text-secondary)] border-[var(--border)]",
  skip: "bg-transparent text-[var(--text-muted)] border-[var(--border)]",
};

type Size = "sm" | "md";

const CHIP: Record<Size, string> = {
  sm: "px-2 py-0.5 text-[10px]",
  md: "px-2.5 py-1 text-[11px]",
};

/**
 * Mylo's judgement on one item — what replaced the percent match.
 *
 * The ring it supersedes carried three jobs at once: the number, the tier colour,
 * and Mylo's portrait as attribution. The number is gone (it implied a
 * measurement nobody made), the tier colour became the verdict's own, and the
 * attribution survives — it is the honest signal that a human-readable judgement
 * exists behind the chip rather than a computed one.
 *
 * A missing verdict renders nothing. The cross-embedding tail has no judgement to
 * show and should not be given a fake one.
 */
export function VerdictBadge({
  verdict,
  origin,
  size = "md",
  scope,
  className,
}: {
  verdict: Verdict | null | undefined;
  /** `llm` puts Mylo's portrait on the chip as attribution. */
  origin?: "llm" | "fallback" | "rules";
  size?: Size;
  /**
   * Whose profile the judgement is about, when it is not the reader's. A lab feed
   * judges items against the *lab's* aggregate interests, and a chip that says
   * nothing invites the reader to take it personally.
   */
  scope?: string;
  className?: string;
}) {
  if (!verdict || verdict === "skip") return null;

  const byMylo = origin === "llm";
  const against = scope ? `${scope}'s research` : "your research";

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border font-semibold uppercase tracking-[0.06em]",
        TONE[verdict],
        CHIP[size],
        className,
      )}
      role="img"
      title={`${VERDICT_LABEL[verdict]} — ${VERDICT_BLURB[verdict]}`}
      aria-label={`${VERDICT_LABEL[verdict]}: ${VERDICT_BLURB[verdict]} Judged against ${against}${
        byMylo ? ", by Mylo" : ""
      }.`}
    >
      {byMylo && size === "md" ? (
        // Attribution rides the chip rather than taking a row of its own.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src="/mylo-portrait-64.webp"
          alt=""
          width={14}
          height={14}
          className="-ml-1 h-3.5 w-3.5 rounded-full object-cover"
        />
      ) : null}
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

/**
 * An item's place in its theme's list.
 *
 * Position is only meaningful *within* a theme: ranking across themes means
 * comparing scores that are not comparable, which is the failure the per-theme
 * feed exists to remove. So the mark says "3rd in Medical AI Agents", never
 * "3rd overall".
 */
export function PositionMark({
  position,
  theme,
  className,
}: {
  position: number | null | undefined;
  /** The theme the position is within — named in the accessible label. */
  theme?: string;
  className?: string;
}) {
  if (typeof position !== "number" || !Number.isFinite(position) || position < 1) {
    return null;
  }
  const within = theme ? `in ${theme}` : "in this list";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-baseline font-semibold tabular-nums text-[var(--text-secondary)]",
        className,
      )}
      aria-label={`Ranked ${ordinal(position)} ${within}`}
      title={`${ordinal(position)} ${within}`}
    >
      <span className="text-[15px] leading-none">{position}</span>
      <span className="text-[9px] leading-none">{suffix(position)}</span>
    </span>
  );
}

function suffix(n: number): string {
  if (n % 100 >= 10 && n % 100 <= 20) return "th";
  return { 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th";
}

function ordinal(n: number): string {
  return `${n}${suffix(n)}`;
}
