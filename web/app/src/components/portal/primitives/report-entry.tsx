"use client";

import * as React from "react";

import { CalendarIcon } from "@/components/portal/icons";
import { matchTier } from "@/components/portal/primitives/match-ring";
import { cn } from "@/lib/utils";

/**
 * The daily report's one entry shape.
 *
 * Every ranked thing the report names — a paper, a grant, a fellowship, a
 * conference, in the written briefing and in the Top-N listings — is this object,
 * and it is the same object in the PDF (see ``_entry_row`` in
 * ``apps/content/daily_report_pdf.py``). The two renderers draw it in different
 * materials; they do not draw different documents.
 *
 * Four zones, in this order:
 *
 * 1. **Rank + title.** A muted gutter numeral and the title. The report is a
 *    ranking and the number says so, but the number is not what the reader is
 *    scanning for, so it recedes.
 * 2. **The insight** — the first sentence of the rationale, in a left-ruled quote
 *    block at primary weight. It answers "why am I looking at this", which is the
 *    only question the entry exists to answer, so it gets the strongest setting in
 *    the content column.
 * 3. **The note** — the rest of the rationale, quieter: the caveat, the
 *    qualification, what actually transfers.
 * 4. **The meta rail** — the match number set large over a tier-coloured bar, its
 *    `MATCH SCORE` caption, then the flags (`NEW`, a venue rank), then the link
 *    out.
 *
 * Beneath the content column sits the **deadline strip**: a thin ruled row
 * carrying the item's dates. Dates used to be a red `Deadline 2026-09-15` wedged
 * under the title, where they competed with the title and still never said *which*
 * round they meant. Here a date is reference material, set as reference material.
 *
 * The percent is a number-and-bar rather than the feed's `MatchRing` because this
 * is a document, not a feed — an arc that sweeps on scroll belongs to a card the
 * reader meets one at a time, and twenty-five of them down a report reads as
 * instrumentation. Both take their tier from the same `matchTier`, so the two
 * surfaces can never disagree about what 95 means.
 */

/** The match number, its tier bar, and the caption naming what the number is. */
export function MatchScore({ percent }: { percent: number | null | undefined }) {
  if (typeof percent !== "number" || !Number.isFinite(percent)) return null;
  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  const { token, word } = matchTier(pct);

  return (
    <div
      /* Full-width so the bar spans the rail rather than shrinking to the width
         of its own caption — the bar is a length the reader compares down the
         page, and a bar whose track changes width entry to entry is not one. */
      className="flex w-full flex-col items-end gap-1"
      role="img"
      aria-label={`${pct} percent match — a ${word} match`}
    >
      <span className="font-serif text-[26px] font-semibold leading-none tabular-nums text-[var(--text-primary)]">
        {pct}
      </span>
      {/* The bar restates the number as a length. Tier colour is never the only
          signal — the number is right above it and the tier word is in the
          accessible name. */}
      <span
        aria-hidden="true"
        className="h-1 w-full overflow-hidden rounded-full bg-[var(--divider)]"
      >
        <span
          className="block h-full rounded-full"
          style={{ width: `${pct}%`, backgroundColor: `var(${token})` }}
        />
      </span>
      <span className="text-[9px] font-semibold uppercase leading-none tracking-[0.09em] text-[var(--text-muted)]">
        Match score
      </span>
    </div>
  );
}

/**
 * One flag in the rail — `NEW`, or a venue rank.
 *
 * `tone="new"` is the entrant marker and carries the report's gold, which
 * `docs/styles.md` reserves for exactly this kind of signal. `tone="neutral"` is
 * everything informational: a CORE/CCF rank is a label, not an opportunity, and
 * giving it gold would put a second alert beside the one that means something.
 */
export function ReportFlag({
  tone = "neutral",
  children,
}: {
  tone?: "new" | "neutral";
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.06em]",
        tone === "new"
          ? "border-[color-mix(in_srgb,var(--accent)_55%,var(--border))] bg-brand-accent-soft text-[color-mix(in_srgb,var(--accent)_78%,var(--text-primary))]"
          : "border-border bg-surface-alt text-[var(--text-secondary)]",
      )}
    >
      {children}
    </span>
  );
}

export type ReportDeadline = {
  /** Already formatted for the reader — never a raw ISO string. */
  date: string;
  /** "Full paper", "Abstract", "Application" — empty when the source didn't say. */
  kind?: string;
  /** The round's own name, when it has one distinct from its kind. */
  label?: string;
};

/** "Full paper" / "Abstract" / … from the collector's deadline-kind vocabulary. */
const DEADLINE_KIND_LABEL: Record<string, string> = {
  abstract: "Abstract",
  manuscript: "Full paper",
  submission: "Submission",
  application: "Application",
  camera_ready: "Camera ready",
  notification: "Notification",
  registration: "Registration",
  event: "Event",
  rebuttal: "Rebuttal",
  review: "Review",
  withdrawal: "Withdrawal",
};

export function deadlineKindText(kind: string | undefined): string {
  if (!kind) return "";
  return DEADLINE_KIND_LABEL[kind] ?? "";
}

/**
 * The entry's dates, as a thin ruled row beneath the content column.
 *
 * Only the nearest round is named. The rest are counted, not listed: a report is
 * read at a glance and a conference with six rounds would otherwise be six lines
 * of dates under a two-line rationale. The feed card is where the full round list
 * — and the per-round alert control that goes with it — lives.
 */
export function DeadlineStrip({
  deadlines,
  extraCount = 0,
}: {
  deadlines: ReportDeadline[];
  /** Rounds beyond the one shown, counted rather than listed. */
  extraCount?: number;
}) {
  const next = deadlines.find((d) => d.date);
  if (!next) return null;

  const kind = deadlineKindText(next.kind) || next.label || "";

  return (
    <p className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-[var(--divider)] pt-2 text-[12px] text-[var(--text-secondary)]">
      <CalendarIcon size={12} aria-hidden="true" />
      <span className="font-semibold text-[var(--text-primary)]">
        Due {next.date}
      </span>
      {kind ? (
        <span className="text-[var(--text-muted)]">· {kind}</span>
      ) : null}
      {extraCount > 0 ? (
        <span className="text-[var(--text-muted)]">
          · +{extraCount} more round{extraCount === 1 ? "" : "s"}
        </span>
      ) : null}
    </p>
  );
}

/**
 * Split a rationale into its insight (the first sentence) and its note (the rest).
 *
 * The rationale is 1-3 model-written sentences, and they are not equal: the first
 * says why the item is here and the rest qualify it. Setting all three at one
 * weight is what made the old entry a paragraph the reader had to parse rather
 * than a claim they could accept or skip.
 *
 * A single-sentence rationale returns an empty note, and the caller renders no
 * second block — not an empty one.
 */
export function splitRationale(text: string): { insight: string; note: string } {
  const trimmed = (text || "").trim();
  if (!trimmed) return { insight: "", note: "" };
  // The first sentence end that is followed by whitespace and more text. The
  // lookahead for a capital or a digit is what keeps "et al." and "vs." from
  // being read as the end of the sentence they sit inside.
  const boundary = /([.!?])\s+(?=["'“(]?[A-Z0-9])/g;
  let match: RegExpExecArray | null;
  while ((match = boundary.exec(trimmed)) !== null) {
    const cut = match.index + 1;
    // Too short to be a sentence on its own — almost always an abbreviation the
    // lookahead could not rule out. Keep looking.
    if (cut < 25) continue;
    return {
      insight: trimmed.slice(0, cut).trim(),
      note: trimmed.slice(cut).trim(),
    };
  }
  return { insight: trimmed, note: "" };
}

/**
 * One ranked entry: gutter, content, rail — and the deadline strip beneath the
 * content column, where a date reads as reference rather than as an alarm.
 */
export function ReportEntry({
  rank,
  title,
  insight,
  note,
  rail,
  flags,
  link,
  deadlines,
  extraDeadlineCount = 0,
  className,
}: {
  /** The visible rank numeral. Presentation only — the `<ol>` carries the order. */
  rank?: React.ReactNode;
  title: React.ReactNode;
  insight?: React.ReactNode;
  note?: React.ReactNode;
  /** The `MatchScore`, or nothing when the item carries no percent. */
  rail?: React.ReactNode;
  flags?: React.ReactNode;
  link?: React.ReactNode;
  deadlines?: ReportDeadline[];
  extraDeadlineCount?: number;
  className?: string;
}) {
  const hasRail = Boolean(rail || flags || link);

  return (
    <div
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 border-b border-[var(--divider)] py-4 last:border-b-0 sm:gap-x-4",
        hasRail && "sm:grid-cols-[auto_minmax(0,1fr)_7.5rem]",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="w-5 shrink-0 pt-0.5 text-right font-serif text-[15px] font-semibold tabular-nums text-[var(--text-muted)]"
      >
        {rank}
      </span>

      <div className="min-w-0">
        <h4 className="font-serif text-[16px] font-semibold leading-snug text-[var(--text-primary)] [text-wrap:pretty]">
          {title}
        </h4>

        {insight ? (
          <div className="mt-2 border-l-2 border-[color-mix(in_srgb,var(--primary)_45%,transparent)] pl-3">
            <p className="text-[14.5px] font-medium leading-relaxed text-[var(--text-primary)] [text-wrap:pretty]">
              {insight}
            </p>
          </div>
        ) : null}

        {note ? (
          <p className="mt-2 text-[13.5px] leading-relaxed text-[var(--text-secondary)] [text-wrap:pretty]">
            {note}
          </p>
        ) : null}

        <DeadlineStrip
          deadlines={deadlines ?? []}
          extraCount={extraDeadlineCount}
        />
      </div>

      {hasRail ? (
        /* On a narrow screen the rail drops under the content column rather than
           squeezing a 7.5rem gutter out of a 320px viewport — it becomes a row,
           reading left to right, which is the only arrangement that still works
           at that width. */
        <div className="col-start-2 mt-3 flex flex-row flex-wrap items-center gap-2 sm:col-start-3 sm:row-start-1 sm:mt-0 sm:flex-col sm:items-end sm:gap-2">
          {rail}
          {flags ? (
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              {flags}
            </div>
          ) : null}
          {link}
        </div>
      ) : null}
    </div>
  );
}
