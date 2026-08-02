"use client";

import * as React from "react";

import { CloseIcon } from "@/components/portal/icons";
import type { ReminderOffset, ReminderUnit } from "@/lib/portal/types";

/** Units offered by the variable "remind me before" builder. */
const UNIT_OPTIONS: { value: ReminderUnit; label: string }[] = [
  { value: "day", label: "days" },
  { value: "week", label: "weeks" },
  { value: "month", label: "months" },
];

/** Seed a new reminder with two common lead times; fully editable/removable. */
export const DEFAULT_OFFSETS: ReminderOffset[] = [
  { amount: 1, unit: "week" },
  { amount: 1, unit: "day" },
];

/** "1 day", "6 days", "4 weeks", "2 months" — a single offset, human-readable. */
export function formatOffset({ amount, unit }: ReminderOffset): string {
  return `${amount} ${unit}${amount === 1 ? "" : "s"}`;
}

export function sameOffset(a: ReminderOffset, b: ReminderOffset): boolean {
  return a.amount === b.amount && a.unit === b.unit;
}

/**
 * The "remind me N days/weeks/months before" builder: a number + a unit, added to
 * a removable chip list. Shared by the composer (setting a reminder) and the
 * reminders page (editing one) so the two surfaces cannot disagree about what a
 * valid lead time is — any whole amount ≥ 1, no duplicates, at least one.
 *
 * Validation messages are raised through `onError` rather than rendered here, so
 * the host form keeps a single error region instead of two competing ones.
 */
export function ReminderOffsetsField({
  offsets,
  onChange,
  onError,
}: {
  offsets: ReminderOffset[];
  onChange: (next: ReminderOffset[]) => void;
  onError: (message: string | null) => void;
}) {
  const [amount, setAmount] = React.useState("2");
  const [unit, setUnit] = React.useState<ReminderUnit>("week");

  const addOffset = () => {
    const n = Number.parseInt(amount, 10);
    if (!Number.isFinite(n) || n < 1) {
      onError("Enter a whole number of at least 1.");
      return;
    }
    const next: ReminderOffset = { amount: n, unit };
    if (offsets.some((o) => sameOffset(o, next))) {
      onError("That reminder time is already added.");
      return;
    }
    onError(null);
    onChange([...offsets, next]);
  };

  const removeOffset = (target: ReminderOffset) => {
    onError(null);
    onChange(offsets.filter((o) => !sameOffset(o, target)));
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5">
        <input
          type="number"
          min={1}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addOffset();
            }
          }}
          aria-label="Amount"
          className="w-16 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value as ReminderUnit)}
          aria-label="Unit"
          className="rounded-lg border border-border bg-surface px-2.5 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {UNIT_OPTIONS.map((u) => (
            <option key={u.value} value={u.value}>
              {u.label}
            </option>
          ))}
        </select>
        <span className="text-[13px] text-[var(--text-secondary)]">before</span>
        <button
          type="button"
          onClick={addOffset}
          className="rounded-full border border-primary bg-primary/10 px-3 py-1.5 text-[12.5px] font-semibold text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Add
        </button>
      </div>

      {offsets.length > 0 ? (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {offsets.map((o) => (
            <span
              key={`${o.amount}-${o.unit}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-alt px-2.5 py-1 text-[12.5px] font-semibold text-[var(--text-secondary)]"
            >
              {formatOffset(o)} before
              <button
                type="button"
                onClick={() => removeOffset(o)}
                aria-label={`Remove ${formatOffset(o)} reminder`}
                className="rounded-full p-0.5 text-[var(--text-secondary)] hover:bg-surface hover:text-[var(--text-primary)]"
              >
                <CloseIcon size={12} />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-[var(--text-secondary)]">
          Add at least one reminder time.
        </p>
      )}
    </div>
  );
}
