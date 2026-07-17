"use client";

import * as React from "react";

import { CloseIcon } from "@/components/portal/icons";
import { useMyLabs, useReminderMutations } from "@/lib/portal/hooks";
import type { DeadlineOption, ReminderOffset } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const OFFSET_PRESETS: { label: string; offset: ReminderOffset }[] = [
  { label: "1 day", offset: { amount: 1, unit: "day" } },
  { label: "3 days", offset: { amount: 3, unit: "day" } },
  { label: "1 week", offset: { amount: 1, unit: "week" } },
  { label: "2 weeks", offset: { amount: 2, unit: "week" } },
  { label: "1 month", offset: { amount: 1, unit: "month" } },
  { label: "3 months", offset: { amount: 3, unit: "month" } },
];

const DEFAULT_SELECTED = new Set(["1 week", "1 day"]);

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

/**
 * A modal to set a deadline reminder from a saved item. The user picks which
 * deadline (a conference has several), whether it's personal or a lab reminder,
 * and how far ahead to be nudged. Rolling/undated deadlines are not offered — the
 * affordance is only shown when at least one deadline has a date.
 */
export function ReminderComposer({
  contentId,
  title,
  deadlines,
  onClose,
}: {
  contentId: string;
  title: string;
  deadlines: DeadlineOption[];
  onClose: () => void;
}) {
  const datedDeadlines = deadlines.filter((d) => d.due_date);
  const [kind, setKind] = React.useState(datedDeadlines[0]?.kind ?? "");
  const [scope, setScope] = React.useState<"personal" | "lab">("personal");
  const [labSlug, setLabSlug] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(
    new Set(DEFAULT_SELECTED),
  );
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

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (label: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  const submit = () => {
    setError(null);
    const offsets = OFFSET_PRESETS.filter((p) => selected.has(p.label)).map(
      (p) => p.offset,
    );
    if (offsets.length === 0) {
      setError("Pick at least one reminder time.");
      return;
    }
    create.mutate(
      {
        content_id: contentId,
        deadline_kind: kind,
        scope,
        lab_slug: scope === "lab" ? effectiveLabSlug : undefined,
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
    !create.isPending &&
    (scope === "personal" || effectiveLabSlug !== "");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
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
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
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
            className="shrink-0 rounded-full p-1 text-[var(--text-muted)] hover:bg-surface-alt hover:text-[var(--text-secondary)]"
          >
            <CloseIcon size={15} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          {datedDeadlines.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)]">
              This item has no fixed deadline, so it can&apos;t be reminded (a
              rolling or continuous deadline has no date to count down to).
            </p>
          ) : (
            <>
              {datedDeadlines.length > 1 ? (
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
                    onChange={(e) => setLabSlug(e.target.value)}
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

              <Field label="Remind me before">
                <div className="flex flex-wrap gap-1.5">
                  {OFFSET_PRESETS.map((p) => (
                    <Chip
                      key={p.label}
                      active={selected.has(p.label)}
                      onClick={() => toggle(p.label)}
                    >
                      {p.label}
                    </Chip>
                  ))}
                </div>
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
        </div>
      </div>
    </div>
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
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
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
