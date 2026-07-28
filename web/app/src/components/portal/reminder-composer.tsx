"use client";

import * as React from "react";

import Link from "next/link";

import { CloseIcon } from "@/components/portal/icons";
import {
  useLabReminderChannels,
  useMyLabs,
  useReminderAccess,
  useReminderMutations,
} from "@/lib/portal/hooks";
import type {
  DeadlineOption,
  ReminderAccess,
  ReminderOffset,
  ReminderUnit,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Units offered by the variable "remind me before" builder. */
const UNIT_OPTIONS: { value: ReminderUnit; label: string }[] = [
  { value: "day", label: "days" },
  { value: "week", label: "weeks" },
  { value: "month", label: "months" },
];

/** Seed the builder with two common lead times; fully editable/removable. */
const DEFAULT_OFFSETS: ReminderOffset[] = [
  { amount: 1, unit: "week" },
  { amount: 1, unit: "day" },
];

const KIND_LABELS: Record<string, string> = {
  application: "Application",
  abstract: "Abstract",
  manuscript: "Manuscript",
  event: "Event",
  other: "Deadline",
};

function formatDue(iso: string | null): string {
  if (!iso) return "no date";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** "1 day", "6 days", "4 weeks", "2 months" — a single offset, human-readable. */
function formatOffset({ amount, unit }: ReminderOffset): string {
  return `${amount} ${unit}${amount === 1 ? "" : "s"}`;
}

function sameOffset(a: ReminderOffset, b: ReminderOffset): boolean {
  return a.amount === b.amount && a.unit === b.unit;
}

/**
 * A modal to set a deadline reminder from a saved item. The user picks which
 * deadline (a conference has several), whether it's personal or a lab reminder,
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
  lockedScope,
  lockedLabSlug,
}: {
  contentId: string;
  title: string;
  deadlines: DeadlineOption[];
  onClose: () => void;
  /** When set, the composer is fixed to a lab reminder for `lockedLabSlug` and
   * the scope/lab pickers are hidden — used from a lab's saved area. */
  lockedScope?: "lab";
  lockedLabSlug?: string;
}) {
  const locked = lockedScope === "lab" && Boolean(lockedLabSlug);
  const datedDeadlines = deadlines.filter((d) => d.due_date);
  const [kind, setKind] = React.useState(datedDeadlines[0]?.kind ?? "");
  const [scope, setScope] = React.useState<"personal" | "lab">(
    locked ? "lab" : "personal",
  );
  const [labSlug, setLabSlug] = React.useState(locked ? lockedLabSlug! : "");
  const [offsets, setOffsets] = React.useState<ReminderOffset[]>(DEFAULT_OFFSETS);
  const [amount, setAmount] = React.useState("2");
  const [unit, setUnit] = React.useState<ReminderUnit>("week");
  // "" = the lab default channel (whatever /setup bound). Lab scope only.
  const [channelId, setChannelId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const labs = useMyLabs();
  // Only labs the caller manages (PI / owner / admin) can receive a lab reminder,
  // mirroring the backend rule — so a plain member is never offered the lab option.
  const labOptions = (labs.data ?? []).filter(
    (lab) => lab.is_lead || lab.role === "owner" || lab.role === "admin",
  );
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

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const addOffset = () => {
    const n = Number.parseInt(amount, 10);
    if (!Number.isFinite(n) || n < 1) {
      setError("Enter a whole number of at least 1.");
      return;
    }
    const next: ReminderOffset = { amount: n, unit };
    if (offsets.some((o) => sameOffset(o, next))) {
      setError("That reminder time is already added.");
      return;
    }
    setError(null);
    setOffsets((prev) => [...prev, next]);
  };

  const removeOffset = (target: ReminderOffset) =>
    setOffsets((prev) => prev.filter((o) => !sameOffset(o, target)));

  const submit = () => {
    setError(null);
    if (offsets.length === 0) {
      setError("Add at least one reminder time.");
      return;
    }
    create.mutate(
      {
        content_id: contentId,
        deadline_kind: kind,
        scope,
        lab_slug: scope === "lab" ? effectiveLabSlug : undefined,
        channel_id_override:
          scope === "lab" && channelId ? channelId : undefined,
        offsets,
      },
      {
        onSuccess: onClose,
        onError: (e) => setError((e as Error).message),
      },
    );
  };

  const canSubmit =
    kind !== "" &&
    offsets.length > 0 &&
    !create.isPending &&
    (scope === "personal" || effectiveLabSlug !== "");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`Set a reminder for ${title}`}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-border bg-surface shadow-[var(--shadow)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-[var(--divider)] px-5 py-3.5">
          <div className="min-w-0">
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Set a reminder
            </p>
            <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-full p-1 text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-secondary)]"
          >
            <CloseIcon size={15} />
          </button>
        </div>

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
                  <div className="flex flex-wrap gap-1.5">
                    {datedDeadlines.map((d) => (
                      <Chip
                        key={d.kind}
                        active={kind === d.kind}
                        onClick={() => setKind(d.kind)}
                      >
                        {KIND_LABELS[d.kind] ?? d.kind} · {formatDue(d.due_date)}
                      </Chip>
                    ))}
                  </div>
                </Field>
              ) : null}

              {locked ? (
                <Field label="Remind">
                  <p className="text-[13px] text-[var(--text-secondary)]">
                    Posts to{" "}
                    <span className="font-semibold text-[var(--text-primary)]">
                      {labOptions.find((l) => l.slug === effectiveLabSlug)?.name ??
                        "this lab"}
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
                    <span className="text-[13px] text-[var(--text-secondary)]">
                      before
                    </span>
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
      </div>
    </div>
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
            href="/app/profile"
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
        <p className="text-[13px] text-[var(--text-secondary)]">Loading channels…</p>
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
