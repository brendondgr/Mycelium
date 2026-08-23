"use client";

import * as React from "react";

import { CalendarIcon } from "@/components/portal/icons";
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
 * 4. **The meta rail** — Mylo's verdict chip and the flags (`NEW`, `ALSO IN`, a
 *    venue rank), all centred on one axis rather than sharing a right edge, so
 *    pills of differing widths do not read as misaligned.
 *
 * The link out sits at the foot of the content column, the way it does on a feed
 * card — a rail narrow enough to hold a ring cannot hold "Open conference" without
 * breaking it across three lines.
 *
 * Beneath the content column sits the **deadline strip**: a thin ruled row
 * carrying the item's dates. Dates used to be a red `Deadline 2026-09-15` wedged
 * under the title, where they competed with the title and still never said *which*
 * round they meant. Here a date is reference material, set as reference material.
 *
 * The verdict is the same `VerdictBadge` the feeds use — the one element this app
 * has for "is this worth my time". A report that invented a second way to show a
 * judgement would read as a different product than the feed beside it, and the
 * PDF draws the same chip in print's own materials.
 *
 * There is no percentage anywhere in it. The ring that used to sit in the rail
 * showed a language model's guess at a similarity next to a real embedding
 * cosine, with nothing to tell a reader which was which; position within a theme
 * and a four-point verdict say the useful part without the false precision.
 */

/**
 * One flag in the rail — `NEW`, or a venue rank.
 *
 * The two are drawn as different *kinds* of pill, not two tints of one: `new` is
 * filled gold, which `docs/styles.md` reserves for signals like this one, and
 * `neutral` is an outline on the page's own ground. A CORE/CCF rank is an
 * informational label rather than an opportunity, and a rank rendered as a second
 * filled badge would compete with the flag that actually means something.
 *
 * `w-fit` is the point of it: a flag is sized to its word. Stretched to the rail
 * it stops reading as a tag and starts reading as a table row.
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
        "inline-flex w-fit items-center gap-1 rounded-full px-2 py-[3px] text-[10px] font-bold uppercase leading-none tracking-[0.06em]",
        tone === "new"
          ? "bg-brand-accent-soft text-[color-mix(in_srgb,var(--accent)_80%,var(--text-primary))]"
          : "border border-border text-[var(--text-muted)]",
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
  /** The verdict chip, or nothing when the item carries no judgement. */
  rail?: React.ReactNode;
  flags?: React.ReactNode;
  link?: React.ReactNode;
  deadlines?: ReportDeadline[];
  extraDeadlineCount?: number;
  className?: string;
}) {
  const hasRail = Boolean(rail || flags);

  return (
    <div
      className={cn(
        "grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 border-b border-[var(--divider)] py-4 last:border-b-0 sm:gap-x-4",
        hasRail && "sm:grid-cols-[auto_minmax(0,1fr)_3.75rem]",
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

        {link ? <div className="mt-2.5">{link}</div> : null}

        <DeadlineStrip
          deadlines={deadlines ?? []}
          extraCount={extraDeadlineCount}
        />
      </div>

      {hasRail ? (
        /* On a narrow screen the rail drops under the content column rather than
           squeezing a fixed gutter out of a 320px viewport — it becomes a row,
           reading left to right, which is the only arrangement that still works
           at that width. */
        <div className="col-start-2 mt-3 flex flex-row flex-wrap items-center gap-2 sm:col-start-3 sm:row-start-1 sm:mt-0 sm:flex-col sm:items-center sm:gap-2">
          {rail}
          {flags ? (
            <div className="flex flex-wrap items-center justify-center gap-1.5">
              {flags}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
