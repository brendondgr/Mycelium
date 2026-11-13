"use client";

import { settingsPath } from "@/lib/portal/settings";
import { useAppHref } from "@/components/demo/demo-context";
import * as React from "react";

import Link from "next/link";

import { MentionPicker } from "@/components/portal/mention-picker";
import { usePersonalOnly } from "@/components/portal/personal-only-scope";
import { Modal, ModalHeader } from "@/components/portal/primitives/modal";
import {
  DEFAULT_OFFSETS,
  ReminderOffsetsField,
} from "@/components/portal/reminder-offsets-field";
import {
  useLabReminderChannels,
  useMyLabs,
  useReminderAccess,
  useReminderMutations,
} from "@/lib/portal/hooks";
import type {
  DeadlineOption,
  MentionTarget,
  Reminder,
  ReminderAccess,
  ReminderOffset,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";
import { CAPABILITY, holding } from "@/lib/portal/capabilities";

const KIND_LABELS: Record<string, string> = {
  application: "Application",
  abstract: "Abstract",
  manuscript: "Full paper",
  event: "The conference itself",
  other: "Deadline",
};

/**
 * `round_label` is free text straight from the source and is not always a round
 * *name*. Alongside the "round 2" and "workshop track" it is meant to carry, the
 * live corpus holds collector provenance notes such as "paper deadline, from
 * content.date free text (Full_Submission is not publicly readable)" — a whole
 * sentence, in a chip the reader is supposed to choose between at a glance.
 *
 * So it is trimmed for display rather than shown raw: everything from the first
 * comma or bracket is dropped (that is reliably where the provenance starts),
 * then capped. The full text stays in the API and in the deadline's own `label`,
 * so nothing is lost — this only decides what fits on a chip.
 */
export function shortRoundLabel(roundLabel: string): string {
  const head = (roundLabel || "").split(/[,(\[]/)[0].trim();
  if (!head) return "";
  return head.length > 36 ? `${head.slice(0, 35).trimEnd()}…` : head;
}

/** How one deadline reads in the picker: the kind, then the source's own round
 * wording when it has one ("Full paper · round 2"). A conference routinely
 * carries several rounds of one kind, so the kind alone would offer the reader
 * two identical-looking chips. */
export function deadlineOptionLabel(d: DeadlineOption): string {
  const kind = KIND_LABELS[d.kind] ?? d.label ?? d.kind;
  const round = shortRoundLabel(d.round_label);
  return round ? `${kind} · ${round}` : kind;
}

/** A stable identity for one deadline option — kind plus round, matching the
 * backend's own uniqueness tuple. `kind` alone is no longer unique. */
export function deadlineOptionId(d: DeadlineOption): string {
  return `${d.kind}::${d.round_key}`;
}

function formatDue(iso: string | null): string {
  if (!iso) return "no date";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * A full-page modal to set a deadline alert. The user picks which deadline (a
 * conference has several rounds), whether it's personal or a lab reminder,
 * and — variably — how far ahead to be nudged (any whole number of days / weeks /
 * months, one or more). A lab reminder may also target a specific channel; left
 * on "Lab default" it posts to whatever channel the manager bound in `/setup`.
 * Rolling/undated deadlines are not offered — the affordance is only shown when at
 * least one deadline has a date.
 */
export function ReminderComposer({
  contentId,
  title,
  deadlines,
  onClose,
  onCreated,
  lockedScope,
  lockedLabSlug,
  initialDeadlineId,
}: {
  contentId: string;
  title: string;
  deadlines: DeadlineOption[];
  onClose: () => void;
  /** Fired with the reminder the server just created, before the modal closes.
   * The card uses it to offer an immediate undo — see `CardActionBar`. */
  onCreated?: (reminder: Reminder) => void;
  /** Pre-select one deadline — set when the composer is opened from a specific
   * row of the card's deadline list, so "set an alert for *this* round" is one
   * gesture rather than open-then-hunt. */
  initialDeadlineId?: string;
  /** When set, the composer is fixed to a lab reminder for `lockedLabSlug` and
   * the scope/lab pickers are hidden — used from a lab's saved area. */
  lockedScope?: "lab";
  lockedLabSlug?: string;
}) {
  const locked = lockedScope === "lab" && Boolean(lockedLabSlug);
  const datedDeadlines = deadlines.filter((d) => d.due_date);
  // Identity is (kind, round), not kind: a conference can carry three full-paper
  // deadlines and each is a separate alert.
  const [selectedId, setSelectedId] = React.useState(() => {
    const preset = initialDeadlineId
      ? datedDeadlines.find((d) => deadlineOptionId(d) === initialDeadlineId)
      : undefined;
    const first = preset ?? datedDeadlines[0];
    return first ? deadlineOptionId(first) : "";
  });
  const selected = datedDeadlines.find(
    (d) => deadlineOptionId(d) === selectedId,
  );
  const [scope, setScope] = React.useState<"personal" | "lab">(
    locked ? "lab" : "personal",
  );
  const [labSlug, setLabSlug] = React.useState(locked ? lockedLabSlug! : "");
  const [offsets, setOffsets] =
    React.useState<ReminderOffset[]>(DEFAULT_OFFSETS);
  // "" = the lab default channel (whatever /setup bound). Lab scope only.
  const [channelId, setChannelId] = React.useState("");
  // Who the lab post @-mentions. Lab scope only: a DM has nobody to tag.
  const [mentions, setMentions] = React.useState<MentionTarget[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const labs = useMyLabs();
  // Only labs the caller manages (PI / owner / admin) can receive a lab reminder,
  // mirroring the backend rule — so a plain member is never offered the lab option.
  // Inside an invite-only project a reminder goes to the person alone, never a
  // lab channel (scoping plan, decision 8).
  const personalOnly = usePersonalOnly();
  const labOptions = personalOnly
    ? []
    : (labs.data ?? []).filter(holding(CAPABILITY.PROFILE_EDIT));
  const { create } = useReminderMutations();

  // Derive the effective lab (no state-syncing effect): the chosen slug, else the
  // first lab. The <select> is controlled by this so it shows a lab by default.
  const effectiveLabSlug = labSlug || labOptions[0]?.slug || "";

  // Reminders need a paid plan and synced Discord — a different answer per scope
  // (your plan + your account for a DM; the lab's plan + its server for a channel),
  // so this follows the scope picker rather than being resolved once for the modal.
  const access = useReminderAccess(
    scope === "lab" ? effectiveLabSlug || undefined : undefined,
  );
  const blocked = access.data ? !access.data.allowed : false;

  // The lab's postable channels — only fetched in lab scope for a managed lab.
  const channels = useLabReminderChannels(
    scope === "lab" ? effectiveLabSlug : undefined,
  );

  const submit = () => {
    setError(null);
    if (offsets.length === 0) {
      setError("Add at least one reminder time.");
      return;
    }
    if (!selected) {
      setError("Choose which deadline to be reminded about.");
      return;
    }
    create.mutate(
      {
        content_id: contentId,
        deadline_kind: selected.kind,
        deadline_round_key: selected.round_key,
        scope,
        lab_slug: scope === "lab" ? effectiveLabSlug : undefined,
        channel_id_override:
          scope === "lab" && channelId ? channelId : undefined,
        mentions: scope === "lab" && mentions.length > 0 ? mentions : undefined,
        offsets,
      },
      {
        onSuccess: (reminder) => {
          onCreated?.(reminder);
          onClose();
        },
        onError: (e) => setError((e as Error).message),
      },
    );
  };

  const canSubmit =
    selected !== undefined &&
    offsets.length > 0 &&
    !create.isPending &&
    (scope === "personal" || effectiveLabSlug !== "");

  return (
    <Modal onClose={onClose} label={`Set an alert for ${title}`}>
      <ModalHeader eyebrow="Set an alert" title={title} onClose={onClose} />
      <div className="space-y-4 px-5 py-4">
        {datedDeadlines.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">
            This item has no fixed deadline, so it can&apos;t be reminded (a
            rolling or continuous deadline has no date to count down to).
          </p>
        ) : (
          <>
            {datedDeadlines.length > 1 && !blocked ? (
              <Field label="Which deadline">
                {/* One chip per *round*, not per kind. A venue with a
                      workshop deadline and two paper rounds shows all four
                      alongside its event date, each separately alertable. */}
                <div className="flex flex-wrap gap-1.5">
                  {datedDeadlines.map((d) => {
                    const id = deadlineOptionId(d);
                    return (
                      <Chip
                        key={id}
                        active={selectedId === id}
                        onClick={() => setSelectedId(id)}
                      >
                        {deadlineOptionLabel(d)} · {formatDue(d.due_date)}
                      </Chip>
                    );
                  })}
                </div>
              </Field>
            ) : datedDeadlines.length === 1 && !blocked ? (
              <Field label="Which deadline">
                <p className="text-[13px] text-[var(--text-secondary)]">
                  <span className="font-semibold text-[var(--text-primary)]">
                    {deadlineOptionLabel(datedDeadlines[0])}
                  </span>{" "}
                  — {formatDue(datedDeadlines[0].due_date)}
                </p>
              </Field>
            ) : null}

            {locked ? (
              <Field label="Remind">
                <p className="text-[13px] text-[var(--text-secondary)]">
                  Posts to{" "}
                  <span className="font-semibold text-[var(--text-primary)]">
                    {labOptions.find((l) => l.slug === effectiveLabSlug)
                      ?.name ?? "this lab"}
                  </span>
                  &apos;s Discord channel.
                </p>
              </Field>
            ) : (
              <>
                <Field label="Remind">
                  <div className="flex gap-1.5">
                    <Chip
                      active={scope === "personal"}
                      onClick={() => setScope("personal")}
                    >
                      Just me (DM)
                    </Chip>
                    <Chip
                      active={scope === "lab"}
                      onClick={() => setScope("lab")}
                      disabled={labOptions.length === 0}
                    >
                      My lab (channel)
                    </Chip>
                  </div>
                </Field>

                {scope === "lab" && labOptions.length > 0 ? (
                  <Field label="Lab">
                    <select
                      value={effectiveLabSlug}
                      onChange={(e) => {
                        setLabSlug(e.target.value);
                        setChannelId(""); // reset to the new lab's default
                      }}
                      className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {labOptions.map((lab) => (
                        <option key={lab.slug} value={lab.slug}>
                          {lab.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                ) : null}
              </>
            )}

            {blocked && access.data ? (
              <ReminderGate access={access.data} onClose={onClose} />
            ) : (
              <>
                {scope === "lab" && effectiveLabSlug ? (
                  <Field label="Tag">
                    <MentionPicker
                      labSlug={effectiveLabSlug}
                      value={mentions}
                      onChange={setMentions}
                    />
                  </Field>
                ) : null}

                {scope === "lab" ? (
                  <ChannelField
                    channels={channels.data?.channels ?? []}
                    defaultId={channels.data?.default_channel_id ?? ""}
                    defaultName={channels.data?.default_channel_name ?? ""}
                    value={channelId}
                    loading={channels.isLoading}
                    onChange={setChannelId}
                  />
                ) : null}

                <Field label="Remind me before">
                  <ReminderOffsetsField
                    offsets={offsets}
                    onChange={setOffsets}
                    onError={setError}
                  />
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
                    disabled={!canSubmit}
                    className="rounded-full bg-primary px-3.5 py-1.5 text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] disabled:opacity-50"
                  >
                    {create.isPending ? "Setting…" : "Set reminder"}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

/**
 * Shown in place of the form when reminders aren't available for the chosen scope.
 *
 * It names both conditions rather than only the blocking one, with the satisfied
 * half checked off, so "what do I actually have to do?" is answered on screen
 * instead of arriving one 403 at a time. The scope picker above stays live, so
 * someone whose own plan is Free can still switch to a lab that is covered.
 */
function ReminderGate({
  access,
  onClose,
}: {
  access: ReminderAccess;
  onClose: () => void;
}) {
  const appHref = useAppHref();
  // A lab the caller doesn't manage: the answer is "not you", not a billing report.
  const isPermission = access.reason === "permission";
  return (
    <div className="rounded-xl border border-border bg-surface-alt p-4">
      <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
        {access.detail}
      </p>
      {isPermission ? null : (
        <>
          <ul className="mt-3 space-y-1.5">
            <GateCondition ok={access.plan_ok} label="An active paid plan" />
            <GateCondition ok={access.discord_ok} label="Discord connected" />
          </ul>
          <Link
            href={appHref(settingsPath({ kind: "you" }, access.plan_ok ? "delivery" : "subscription"))}
            onClick={onClose}
            className="mt-3.5 inline-flex rounded-full border border-primary bg-primary/10 px-3.5 py-1.5 text-[12.5px] font-semibold text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {access.plan_ok ? "Connect Discord" : "See your plan"}
          </Link>
        </>
      )}
    </div>
  );
}

/** One condition in the gate list — met or not, in words, never colour alone. */
function GateCondition({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-[12.5px]">
      <span
        aria-hidden="true"
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
          ok
            ? "bg-[var(--success)] text-[var(--destructive-foreground)]"
            : "border border-border text-[var(--text-secondary)]",
        )}
      >
        {ok ? "✓" : "—"}
      </span>
      <span
        className={
          ok ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)]"
        }
      >
        {label}
        <span className="sr-only">
          {ok ? " — already set up" : " — still needed"}
        </span>
      </span>
    </li>
  );
}

/**
 * The lab channel picker. "Lab default" (value "") posts to the channel the
 * manager bound in `/setup`; other options override it for this reminder only.
 * When no channels can be listed (guild unlinked or Discord unreachable), it
 * collapses to a note — the reminder still posts to the lab default.
 */
function ChannelField({
  channels,
  defaultId,
  defaultName,
  value,
  loading,
  onChange,
}: {
  channels: { id: string; name: string }[];
  defaultId: string;
  defaultName: string;
  value: string;
  loading: boolean;
  onChange: (id: string) => void;
}) {
  const defaultLabel = defaultName
    ? `Lab default (#${defaultName})`
    : "Lab default channel";

  if (loading) {
    return (
      <Field label="Channel">
        <p className="text-[13px] text-[var(--text-secondary)]">
          Loading channels…
        </p>
      </Field>
    );
  }

  // Non-default channels the user can choose instead of the /setup default.
  const others = channels.filter((c) => c.id !== defaultId);
  if (others.length === 0) {
    return (
      <Field label="Channel">
        <p className="text-[13px] text-[var(--text-secondary)]">
          Posts to the lab&apos;s{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            {defaultName ? `#${defaultName}` : "default"}
          </span>{" "}
          channel (set in Discord with{" "}
          <span className="font-mono text-[12px]">/setup</span>).
        </p>
      </Field>
    );
  }

  return (
    <Field label="Channel">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">{defaultLabel}</option>
        {others.map((c) => (
          <option key={c.id} value={c.id}>
            #{c.name}
          </option>
        ))}
      </select>
    </Field>
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

function Chip({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-full border px-3 py-1.5 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40",
        active
          ? "border-primary bg-primary text-[#fffdf8]"
          : "border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-primary)]",
      )}
    >
      {children}
    </button>
  );
}
