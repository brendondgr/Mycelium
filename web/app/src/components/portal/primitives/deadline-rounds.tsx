import * as React from "react";

import { InfoPopover } from "@/components/portal/primitives/info-popover";

/** One row of the multi-deadline hover — already formatted for display. */
export type DeadlineRound = {
  key: string;
  /** e.g. "Abstract", "Full paper — Round 2", "Round 1". */
  label: string;
  /** Pre-formatted date text, or the source's own verbatim wording when no
   * date could be parsed. */
  dateLabel: string;
  /** True when this round's date was estimated/inferred rather than read
   * verbatim off the source — shown as a quiet "(est.)" suffix, never hidden. */
  estimated?: boolean;
};

/**
 * The multi-deadline hover (plan D1) — shared by the grant and conference
 * cards, since both carry a full round array behind their single actionable
 * `deadline_date`: conferences via `deadlines_structured`, grants via
 * `due_dates`. Each card builds its own `DeadlineRound[]` (the two source
 * shapes differ — a conference round has a kind and an ISO instant, a grant
 * round is a bare ISO date) and this renders the shared list + keyboard/
 * touch-accessible disclosure on top of `InfoPopover`.
 */
export function DeadlineRoundsButton({
  trigger,
  triggerLabel,
  triggerClassName,
  rounds,
  footnote,
}: {
  trigger: React.ReactNode;
  triggerLabel: string;
  triggerClassName?: string;
  rounds: DeadlineRound[];
  /** Extra context below the round list (a letter-of-intent date, the first
   * ever-posted deadline before it moved, …). */
  footnote?: React.ReactNode;
}) {
  return (
    <InfoPopover
      trigger={trigger}
      triggerLabel={triggerLabel}
      triggerClassName={triggerClassName}
    >
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">
        {rounds.length > 1 ? `All ${rounds.length} deadlines` : "Deadline"}
      </p>
      <ul className="mt-1.5 space-y-1.5">
        {rounds.map((round) => (
          <li key={round.key} className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 text-[var(--text-primary)]">{round.label}</span>
            <span className="shrink-0 tabular-nums text-[var(--text-secondary)]">
              {round.dateLabel}
              {round.estimated ? (
                <span className="ml-1 text-[var(--text-muted)]">(est.)</span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      {footnote ? (
        <div className="mt-2 space-y-1 border-t border-[var(--divider)] pt-2">
          {footnote}
        </div>
      ) : null}
    </InfoPopover>
  );
}
