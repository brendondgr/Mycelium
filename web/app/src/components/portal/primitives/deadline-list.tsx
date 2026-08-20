"use client";

import * as React from "react";

import {
  BellIcon,
  CalendarIcon,
  CheckIcon,
  ChevronDownIcon,
} from "@/components/portal/icons";
import {
  ReminderComposer,
  deadlineOptionId,
  deadlineOptionLabel,
} from "@/components/portal/reminder-composer";
import { formatIsoDate } from "@/lib/portal/dates";
import { useDismissable } from "@/lib/portal/use-dismissable";
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
 * The card's **Deadlines** control: a button carrying the next upcoming
 * deadline, which opens onto every other round — each future one with its own
 * alert control.
 *
 * It sits directly beneath the card's three tools and spans their combined
 * width, so the head reads as one block of actions rather than a row of icons
 * with a date list orbiting it. The full list used to run the card's whole
 * width below the head, which gave every dated item a permanent three-to-six
 * row table above its description; only the next date is needed at a glance,
 * and everything else is one click away.
 *
 * The trigger is uncoloured at rest and takes the gold deadline tint on hover
 * or focus, matching the tools above it (`docs/styles.md` reserves gold for
 * opportunity signals, which a deadline is). It opens on click and stays open
 * until an outside click or Escape — not on hover, which would be unreachable
 * by touch and would flicker the panel shut as the pointer crossed the gap.
 *
 * Nothing renders at all when an item has no deadlines — a rolling call, a
 * paper — rather than an empty control explaining its own emptiness.
 */
export function DeadlineMenu({
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
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const [composingFor, setComposingFor] = React.useState<string | null>(null);

  const dated = React.useMemo(
    () =>
      deadlines
        .filter((d) => d.due_date)
        .slice()
        .sort((a, b) => (a.due_date! < b.due_date! ? -1 : 1)),
    [deadlines],
  );

  if (dated.length === 0 && extraDeadlines.length === 0) return null;

  // The next upcoming deadline is what the button says. `is_next` is the
  // backend's own mark, but a card can carry one per kind (abstract *and*
  // paper), so the earliest of them is what "next" means to a reader.
  const next = dated[0];
  const upcomingExtra = extraDeadlines.find((round) => !round.passed);
  const triggerText = next
    ? formatIsoDate(next.due_date!)
    : upcomingExtra
      ? upcomingExtra.dateLabel
      : "All passed";
  const triggerDescription = next
    ? `${deadlineOptionLabel(next)} — ${triggerText}`
    : upcomingExtra
      ? `${upcomingExtra.label} — ${triggerText}`
      : "Every deadline on record has passed";
  const rowCount = dated.length + extraDeadlines.length;

  return (
    <div ref={ref} className="relative w-full">
      <p className="text-right text-[9.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {rowCount > 1 ? "Deadlines" : "Deadline"}
      </p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Deadlines for ${title} — next, ${triggerDescription}`}
        title={triggerDescription}
        className={cn(
          "mt-1 inline-flex w-full items-center justify-between gap-1 rounded-full border px-2 py-1 text-[11px] font-semibold tabular-nums transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          open
            ? "border-[color-mix(in_srgb,var(--accent)_55%,transparent)] bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] text-[var(--text-primary)]"
            : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[color-mix(in_srgb,var(--accent)_50%,transparent)] hover:bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] hover:text-[var(--text-primary)]",
        )}
      >
        <CalendarIcon size={11} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-left">{triggerText}</span>
        <ChevronDownIcon
          size={11}
          aria-hidden="true"
          className={cn(
            "shrink-0 transition-transform duration-150 motion-reduce:transition-none",
            open && "rotate-180",
          )}
        />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-40 w-[min(20rem,78vw)] rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-3 text-left shadow-[var(--shadow)]"
        >
          <DeadlineRows
            title={title}
            dated={dated}
            extraDeadlines={extraDeadlines}
            footnote={footnote}
            lockedLabSlug={lockedLabSlug}
            onCompose={setComposingFor}
          />
        </div>
      ) : null}

      {/* Rendered outside the panel so dismissing the dropdown (an outside
          click lands in the modal) cannot unmount the composer under itself. */}
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

/**
 * Every round the item carries, one per row: the alertable ones first, each
 * with its own alert control pointed at that round, then the display-only
 * rows (passed rounds struck through, later grant rounds plain).
 */
function DeadlineRows({
  title,
  dated,
  extraDeadlines,
  footnote,
  lockedLabSlug,
  onCompose,
}: {
  title: string;
  dated: DeadlineOption[];
  extraDeadlines: ExtraDeadline[];
  footnote?: React.ReactNode;
  lockedLabSlug?: string;
  onCompose: (id: string) => void;
}) {
  // One shared query for the whole card: the alert controls stay visible and
  // clickable when the plan doesn't cover them, because a missing button
  // teaches nothing — the composer names which condition is unmet.
  const access = useReminderAccess(lockedLabSlug);
  const blocked = access.data ? !access.data.allowed : false;

  return (
    <>
      <ul className="space-y-1">
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
                  onClick={() => onCompose(id)}
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
    </>
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
