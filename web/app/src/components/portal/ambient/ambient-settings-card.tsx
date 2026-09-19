"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import {
  useAmbientSettings,
  useDeleteObservations,
  useSaveAmbientSettings,
} from "@/lib/portal/ambient/hooks";
import type { AmbientSettings } from "@/lib/portal/ambient/types";

/**
 * Mylo & you — the switches (ambient Plan 07, step 8).
 *
 * Listening per platform, the single "shut off Mylo's questions" switch (the
 * same one "stop asking" flips in a DM), a quiet period, the plain statement of
 * what is stored, and "delete my observations". On a free plan the panel is
 * shown read-only with one sentence: nothing is collected.
 */
export function AmbientSettingsCard() {
  const settings = useAmbientSettings();
  return (
    <Card className="p-[22px]" aria-labelledby="ambient-settings-title" data-ambient="settings">
      <h2 id="ambient-settings-title" className="font-display text-lg text-[var(--text-primary)]">
        Mylo &amp; your conversations
      </h2>
      {settings.isLoading ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : settings.isError || !settings.data ? (
        <p className="mt-3 text-sm text-clay">Couldn&apos;t load these settings.</p>
      ) : (
        <SettingsBody key={JSON.stringify(settings.data)} data={settings.data} />
      )}
    </Card>
  );
}

function SettingsBody({ data }: { data: AmbientSettings }) {
  const save = useSaveAmbientSettings();
  const wipe = useDeleteObservations();
  const [quiet, setQuiet] = React.useState(data.quiet_until ?? "");
  const [confirming, setConfirming] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const readOnly = !data.paid || !data.available;

  const update = (body: Parameters<typeof save.mutate>[0], done: string) => {
    setMessage(null);
    save.mutate(body, {
      onSuccess: () => setMessage(done),
      onError: (error) => setMessage(error.message),
    });
  };

  return (
    <div className="mt-3 space-y-4">
      <p className="max-w-[62ch] rounded-lg border border-border bg-surface-alt/60 px-3 py-2 text-[13px] leading-relaxed text-[var(--text-secondary)]">
        {data.statement}
      </p>
      {!data.available ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Listening isn&apos;t turned on for this Mycelium yet. Nothing is collected.
        </p>
      ) : !data.paid ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Mylo learning from your conversations is part of the paid plan. On your plan,
          nothing is collected.
        </p>
      ) : !data.linked ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Link your Discord account on your profile to turn this on.
        </p>
      ) : null}

      <fieldset className="space-y-3" disabled={save.isPending}>
        <legend className="sr-only">Listening and questions</legend>
        <Toggle
          id="ambient-listening"
          label="Listen on Discord"
          help="Read what you say in servers that allow it and in your messages to Mylo. Off by default."
          checked={data.listening.discord}
          disabled={readOnly && !data.listening.discord}
          onChange={(on) =>
            update({ listening_discord: on }, on ? "Listening is on." : "Listening is off.")
          }
        />
        <Toggle
          id="ambient-questions"
          label="Mylo's questions"
          help="Now and then Mylo asks whether it read something right. Turn off to stop them — what it already understood stays."
          checked={!data.questions_muted}
          disabled={readOnly}
          onChange={(on) =>
            update({ questions_muted: !on }, on ? "Questions are back on." : "No more questions.")
          }
        />
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm text-[var(--text-primary)]" htmlFor="ambient-quiet">
            <span className="block font-medium">Quiet until</span>
            <span className="block text-xs text-[var(--text-muted)]">
              No questions before this date.
            </span>
            <input
              id="ambient-quiet"
              type="date"
              value={quiet}
              disabled={readOnly}
              onChange={(event) => setQuiet(event.target.value)}
              className="mt-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            />
          </label>
          <button
            type="button"
            disabled={readOnly || save.isPending}
            onClick={() =>
              update({ quiet_until: quiet || null }, quiet ? `Quiet until ${quiet}.` : "No quiet period.")
            }
            className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
          >
            Save
          </button>
        </div>
      </fieldset>

      <div className="border-t border-[var(--divider)] pt-4">
        <p className="text-sm text-[var(--text-secondary)]">
          Mylo holds {data.observations} short {data.observations === 1 ? "summary" : "summaries"} from
          your conversations.
        </p>
        {confirming ? (
          <div className="mt-2 flex flex-wrap items-center gap-2" role="group" aria-label="Confirm deletion">
            <span className="text-sm text-clay">
              Delete every summary and everything Mylo understood from them? This can&apos;t be undone.
            </span>
            <button
              type="button"
              onClick={() =>
                wipe.mutate(undefined, {
                  onSuccess: (result) => {
                    setConfirming(false);
                    setMessage(`Deleted ${result.deleted_observations} summaries.`);
                  },
                  onError: (error) => setMessage(error.message),
                })
              }
              disabled={wipe.isPending}
              className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-clay hover:bg-surface-alt disabled:opacity-60"
            >
              Yes, delete
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-sm font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
            >
              Keep them
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={data.observations === 0}
            className="mt-2 rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-clay hover:bg-surface-alt disabled:opacity-60"
          >
            Delete my observations
          </button>
        )}
      </div>
      <p aria-live="polite" className="min-h-[1.25rem] text-sm text-[var(--text-secondary)]">
        {message}
      </p>
    </div>
  );
}

function Toggle({
  id,
  label,
  help,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <div className="flex items-start gap-3">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={`${id}-help`}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 motion-reduce:transition-none ${
          checked ? "bg-primary" : "bg-surface-alt"
        }`}
      >
        <span className="sr-only">{label}</span>
        <span
          aria-hidden="true"
          className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-surface shadow transition-transform motion-reduce:transition-none ${
            checked ? "translate-x-[22px]" : "translate-x-0.5"
          }`}
        />
      </button>
      <div>
        <label htmlFor={id} className="text-sm font-medium text-[var(--text-primary)]">
          {label}
        </label>
        <p id={`${id}-help`} className="text-xs text-[var(--text-muted)]">
          {help}
        </p>
      </div>
    </div>
  );
}
