"use client";

import * as React from "react";

import { Modal, ModalHeader } from "@/components/portal/primitives/modal";
import { ReminderOffsetsField } from "@/components/portal/reminder-offsets-field";
import {
  useLabReminderChannels,
  useReminderMutations,
} from "@/lib/portal/hooks";
import type { Reminder, ReminderOffset } from "@/lib/portal/types";

/** Today as `YYYY-MM-DD`, local — the floor for the snooze date input. */
function todayIso(): string {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return now.toISOString().slice(0, 10);
}

/**
 * Edit an existing reminder from the reminders page: its lead times, the lab
 * channel it posts to, and how long it stays paused.
 *
 * Deliberately narrower than the composer — what a reminder is *for* (the item and
 * which of its deadlines) is fixed at creation, since changing that would make it a
 * different reminder. Everything it sends to the server goes through the same
 * `PATCH` that only carries the keys the user actually touched.
 */
export function ReminderEditor({
  reminder,
  onClose,
}: {
  reminder: Reminder;
  onClose: () => void;
}) {
  const [offsets, setOffsets] = React.useState<ReminderOffset[]>(
    reminder.offsets.map((o) => ({ amount: o.amount, unit: o.unit })),
  );
  const [channelId, setChannelId] = React.useState(
    reminder.channel_id_override,
  );
  const [snooze, setSnooze] = React.useState(reminder.snoozed_until ?? "");
  const [error, setError] = React.useState<string | null>(null);

  const { update } = useReminderMutations();
  const isLab = reminder.scope === "lab";
  const channels = useLabReminderChannels(
    isLab ? (reminder.lab_slug ?? undefined) : undefined,
  );

  const submit = () => {
    setError(null);
    if (offsets.length === 0) {
      setError("Add at least one reminder time.");
      return;
    }
    update.mutate(
      {
        id: reminder.id,
        input: {
          offsets,
          ...(isLab ? { channel_id_override: channelId } : {}),
          // "" means the field was cleared, which is an explicit un-snooze —
          // distinct from never having touched it, so it is still sent (as null).
          snoozed_until: snooze === "" ? null : snooze,
        },
      },
      {
        onSuccess: onClose,
        onError: (e) => setError((e as Error).message),
      },
    );
  };

  const channelOptions = channels.data?.channels ?? [];
  const defaultName = channels.data?.default_channel_name ?? "";

  return (
    <Modal onClose={onClose} label={`Edit the alert for ${reminder.title}`}>
      <ModalHeader
        eyebrow={
          reminder.round_label
            ? `Edit alert · ${reminder.round_label}`
            : "Edit alert"
        }
        title={reminder.title}
        onClose={onClose}
      />
      <div className="space-y-4 px-5 py-4">
        <Field label="Remind me before">
          <ReminderOffsetsField
            offsets={offsets}
            onChange={setOffsets}
            onError={setError}
          />
        </Field>

        {isLab ? (
          <Field label="Channel">
            {channelOptions.length === 0 ? (
              <p className="text-[13px] text-[var(--text-secondary)]">
                Posts to the lab&apos;s{" "}
                <span className="font-semibold text-[var(--text-primary)]">
                  {defaultName ? `#${defaultName}` : "default"}
                </span>{" "}
                channel.
              </p>
            ) : (
              <select
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">
                  {defaultName
                    ? `Lab default (#${defaultName})`
                    : "Lab default channel"}
                </option>
                {channelOptions
                  .filter((c) => c.id !== channels.data?.default_channel_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      #{c.name}
                    </option>
                  ))}
              </select>
            )}
          </Field>
        ) : null}

        <Field label="Pause until">
          <input
            type="date"
            value={snooze}
            min={todayIso()}
            max={reminder.due_date ?? undefined}
            onChange={(e) => setSnooze(e.target.value)}
            aria-label="Pause reminders until"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <p className="mt-1.5 text-[12px] text-[var(--text-secondary)]">
            Nothing sends before this date; any lead time it passes still
            arrives afterwards, with the real days remaining. Clear the field to
            resume now.
          </p>
        </Field>

        {error ? (
          <p className="text-[12.5px] text-clay" role="alert">
            {error}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={update.isPending || offsets.length === 0}
            className="rounded-full bg-primary px-3.5 py-1.5 text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] disabled:opacity-50"
          >
            {update.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {label}
      </p>
      {children}
    </div>
  );
}
