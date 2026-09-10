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
 *
 * That distinction is also why the mark carries a denominator when it has one.
 * The feed interleaves themes, so a 10th can sit directly above a 3rd and look
 * like a sorting bug; "10 of 25" says plainly that the two numbers are counts in
 * different lists. `of` is the slate's *realised* length, so a theme that only
 * produced seven candidates reads "of 7" — a row written before slates recorded
 * their length carries none, and the bare ordinal renders instead of a guess.
 *
 * The numeral is set in the card's own serif (`--font-serif`, Fraunces) with the
 * suffix raised off it, so the mark reads as a piece of the card's typography
 * rather than as a scoreboard sitting beside it.
 */
export function PositionMark({
  position,
  of,
  theme,
  className,
}: {
  position: number | null | undefined;
  /** How long the theme's slate ran; omitted when the row does not record it. */
  of?: number | null;
  /** The theme the position is within — named in the accessible label. */
  theme?: string;
  className?: string;
}) {
  if (typeof position !== "number" || !Number.isFinite(position) || position < 1) {
    return null;
  }
  // A denominator below the position itself would be arithmetic nonsense, and is
  // the shape a stale row takes when only one of the two numbers has been
  // rewritten — so it is dropped rather than printed.
  const total =
    typeof of === "number" && Number.isFinite(of) && of >= position ? of : null;
  const within = theme ? `in ${theme}` : "in this list";
  const spoken = total
    ? `Ranked ${ordinal(position)} of ${total} ${within}`
    : `Ranked ${ordinal(position)} ${within}`;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 flex-col items-center leading-none",
        className,
      )}
      aria-label={spoken}
      title={spoken}
    >
      <span className="font-serif text-[21px] font-semibold tabular-nums leading-none text-[var(--text-primary)]">
        {position}
        <sup className="ml-px align-super text-[9px] font-medium leading-none text-[var(--text-muted)]">
          {suffix(position)}
        </sup>
      </span>
      {total ? (
        <span
          aria-hidden="true"
          className="mt-0.5 text-[10px] tabular-nums leading-none text-[var(--text-muted)]"
        >
          of {total}
        </span>
      ) : null}
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
