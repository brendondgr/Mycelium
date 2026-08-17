"use client";

import * as React from "react";

import { BellIcon, CalendarIcon, CheckIcon } from "@/components/portal/icons";
import {
  ReminderComposer,
  deadlineOptionId,
  deadlineOptionLabel,
} from "@/components/portal/reminder-composer";
import { formatIsoDate } from "@/components/portal/sections/opportunity-bits";
import { useReminderAccess } from "@/lib/portal/hooks";
import type { DeadlineOption } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * A deadline shown for context but not alertable.
 *
 * Two cases, deliberately one type. A round that has **passed** — struck
 * through, because "I missed round 1, when is round 2" is a real question and
 * hiding the answer makes the list look wrong rather than complete. And a
 * future round the backend does not project as separately addressable: a grant
 * keeps one application row (its next round), so its later rounds are real
 * dates a reader should see even though only the next one can carry an alert.
 */
export type ExtraDeadline = {
  key: string;
  label: string;
  /** Pre-formatted, or the source's own verbatim wording when undated. */
  dateLabel: string;
  estimated?: boolean;
  /** Already gone by — struck through and announced as such. */
  passed?: boolean;
};

/**
 * Every deadline an item carries, as a list, sitting with Save and Set an alert.
 *
 * This replaces a hover popover behind a separate button. Two things were wrong
 * with that. Seeing what deadlines a conference actually has — the thing the
 * reader is on this page for — took a deliberate click into a transient
 * disclosure; and the alert control lived somewhere else entirely, so choosing
 * *which* deadline to be alerted about meant opening one surface to read the
 * rounds and a different one to act on them.
 *
 * Here each round is a row, and each row that is still ahead carries its own
 * alert control which opens the composer already pointed at that round. Rounds
 * that have passed stay visible, struck through and unalertable, because "I
 * missed round 1, when is round 2" is a real question and hiding the answer
 * makes the list look wrong rather than complete.
 *
 * Nothing renders at all when an item has no deadlines — a rolling call, a
 * paper — rather than an empty box explaining its own emptiness.
 */
export function DeadlineList({
  contentId,
  title,
  deadlines,
  extraDeadlines = [],
  footnote,
  lockedLabSlug,
}: {
  contentId: string;
  title: string;
  /** The addressable (future, dated) deadlines — one per round. */
  deadlines: DeadlineOption[];
  /** Display-only rows: passed rounds, and future ones that carry no alert. */
  extraDeadlines?: ExtraDeadline[];
  /** Extra context under the list (a letter-of-intent date, a moved deadline). */
  footnote?: React.ReactNode;
  /** Set from a lab's Saves area so the alert posts to that lab's channel. */
  lockedLabSlug?: string;
}) {
  const [composingFor, setComposingFor] = React.useState<string | null>(null);
  // One shared query for the whole card: the alert controls stay visible and
  // clickable when the plan doesn't cover them, because a missing button
  // teaches nothing — the composer names which condition is unmet.
  const access = useReminderAccess(lockedLabSlug);
  const blocked = access.data ? !access.data.allowed : false;

  const dated = deadlines.filter((d) => d.due_date);
  if (dated.length === 0 && extraDeadlines.length === 0) return null;

  const heading =
    dated.length + extraDeadlines.length > 1 ? "Deadlines" : "Deadline";

  return (
    <div className="mt-3 rounded-xl border border-[var(--border)] bg-[var(--surface-alt)] p-3">
      <div className="flex items-center gap-1.5">
        <CalendarIcon size={13} aria-hidden="true" />
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {heading}
        </p>
      </div>

      <ul className="mt-2 space-y-1">
        {dated.map((deadline) => {
          const id = deadlineOptionId(deadline);
          return (
            <li
              key={id}
              className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 rounded-lg px-1 py-1"
            >
              <span className="min-w-0 text-[13px] text-[var(--text-primary)]">
                {deadlineOptionLabel(deadline)}
                {deadline.confidence === "anticipated" ? (
                  <span
                    className="ml-1 text-[var(--text-muted)]"
                    title="Mylo projected this date rather than reading it"
                  >
                    (est.)
                  </span>
                ) : null}
              </span>
              <span className="flex shrink-0 items-baseline gap-2">
                <span className="text-[13px] font-semibold tabular-nums text-[var(--destructive)]">
                  {formatIsoDate(deadline.due_date!)}
                </span>
                <button
                  type="button"
                  onClick={() => setComposingFor(id)}
                  // Names the deadline, not just the item: several of these sit
                  // in one list and "Set an alert" alone is the same accessible
                  // name repeated, which is unusable by voice or screen reader.
                  aria-label={
                    blocked
                      ? `Alerts unavailable for ${deadlineOptionLabel(deadline)} — see what's needed`
                      : `Set an alert for ${deadlineOptionLabel(deadline)} on ${title}`
                  }
                  title={
                    blocked
                      ? access.data?.detail ||
                        "Alerts aren't available on your plan"
                      : "Set an alert for this deadline"
                  }
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    blocked
                      ? "border-border bg-surface text-[var(--text-secondary)] opacity-70 hover:opacity-100"
                      : "border-transparent bg-[#3f6fa3] text-white hover:bg-[#345c85]",
                  )}
                >
                  <BellIcon size={10} aria-hidden="true" />
                  Alert
                </button>
              </span>
            </li>
          );
        })}

        {extraDeadlines.map((round) => (
          <li
            key={round.key}
            className={cn(
              "flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-1 py-1 text-[13px]",
              round.passed
                ? "text-[var(--text-muted)]"
                : "text-[var(--text-secondary)]",
            )}
          >
            <span className={cn("min-w-0", round.passed && "line-through")}>
              {round.label}
            </span>
            <span className="shrink-0 tabular-nums">
              {round.dateLabel}
              {round.estimated ? <span className="ml-1">(est.)</span> : null}
              {round.passed ? (
                <span className="sr-only"> — already passed</span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>

      {footnote ? (
        <div className="mt-2 space-y-1 border-t border-[var(--divider)] px-1 pt-2 text-[12px] text-[var(--text-secondary)]">
          {footnote}
        </div>
      ) : null}

      {dated.length === 0 ? (
        <p className="mt-1.5 px-1 text-[12px] text-[var(--text-secondary)]">
          Every deadline on record has passed — nothing left to be alerted
          about.
        </p>
      ) : null}

      {composingFor ? (
        <ReminderComposer
          contentId={contentId}
          title={title}
          deadlines={dated}
          initialDeadlineId={composingFor}
          onClose={() => setComposingFor(null)}
          lockedScope={lockedLabSlug ? "lab" : undefined}
          lockedLabSlug={lockedLabSlug}
        />
      ) : null}
    </div>
  );
}

/** A tick beside a still-open submission window, reused by the feed cards. */
export function OpenMarker({ label }: { label: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
      style={{
        borderColor: "color-mix(in srgb, var(--success) 35%, var(--border))",
        backgroundColor:
          "color-mix(in srgb, var(--success) 10%, var(--surface))",
        color: "var(--text-primary)",
      }}
    >
      <CheckIcon size={11} aria-hidden="true" />
      {label}
    </span>
  );
}
