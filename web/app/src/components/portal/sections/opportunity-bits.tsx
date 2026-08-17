"use client";

import * as React from "react";

import {
  BellIcon,
  BookmarkIcon,
  CheckIcon,
  ChevronDownIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import { ReminderComposer } from "@/components/portal/reminder-composer";
import {
  useMyLabs,
  useReminderAccess,
  useSaveOpportunity,
} from "@/lib/portal/hooks";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type { DeadlineOption, MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** A member with owner/admin/PI rights may save to that lab's shared saves. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/**
 * Mylo's read on why an opportunity fits — the LLM's tailored explanation in a
 * soft green field led by Mylo's headshot. Shared across the Grants,
 * Conferences, and Fellowships cards so the AI note reads identically wherever
 * the language model wrote it (origin === "llm").
 */
export function MyloReason({ reason }: { reason: string }) {
  return (
    <div
      className="mt-3 flex items-start gap-2.5 rounded-xl border p-3"
      style={{
        borderColor: "color-mix(in srgb, var(--primary) 30%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--primary) 8%, transparent)",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/mylo-portrait-64.webp"
        alt=""
        width={24}
        height={24}
        className="mt-0.5 h-6 w-6 shrink-0 rounded-full object-cover"
      />
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        {reason}
      </p>
    </div>
  );
}

/**
 * The "New" tag for a freshly-seen item pinned to the top for its first week.
 * A solid green pill (with an icon + text, never color alone) so it's unmistakable.
 */
export function NewTag() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold"
      style={{
        backgroundColor: "var(--success)",
        color: "var(--destructive-foreground)",
      }}
    >
      <SparkleIcon size={12} aria-hidden="true" />
      New
    </span>
  );
}

/**
 * The "Updated" tag: this listing was already here, but its source page moved
 * something a reader can act on — a deadline added, moved, or the call
 * reopened.
 *
 * Deliberately not the "New" tag. Conferences and grants are largely extracted
 * from pages that host many events at once, and when such a page is updated the
 * old entries stay on it, so "the page changed" is not "this arrived". Calling
 * it new would misstate what happened, and the two are mutually exclusive by
 * construction on the backend. Quieter than New — an outlined amber pill rather
 * than a solid green one — because it is a nudge to re-read something, not an
 * arrival.
 */
export function UpdatedTag({ reason }: { reason?: string }) {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold"
      style={{
        borderColor: "color-mix(in srgb, var(--warning) 50%, var(--border))",
        backgroundColor:
          "color-mix(in srgb, var(--warning) 12%, var(--surface))",
        color: "var(--text-primary)",
      }}
      title={
        reason
          ? `The source listing changed: ${reason.replace(/_/g, " ")}`
          : "The source listing changed since Mylo last read it"
      }
    >
      <RefreshGlyph />
      Updated
    </span>
  );
}

/** Inline so the tag needs no new entry in the shared icon set. */
function RefreshGlyph() {
  return (
    <svg
      width={11}
      height={11}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6" />
    </svg>
  );
}

/**
 * Format a date-only `YYYY-MM-DD` string as "Nov 12, 2026", in local time.
 *
 * `new Date("2026-09-10")` is **not** what you want here. ECMAScript reads the
 * date-only form as UTC midnight, so every timezone behind UTC renders the day
 * before: in America/New_York that exact string prints "Sep 9, 2026". A
 * deadline shown a day early is the worst direction for this product to be
 * wrong in — the whole corpus is deadlines, and a reader who trusts the card
 * submits late.
 *
 * Splitting the parts and going through the local-time `Date(y, m, d)`
 * constructor keeps the calendar date the backend sent. The backend sends a
 * plain calendar date on purpose: a funder's "due Nov 12" is a calendar day in
 * the funder's own world, not an instant, and re-projecting it through the
 * reader's timezone invents precision nobody wrote down.
 *
 * Use this for `deadline_date`, `posted`, `due_dates[]` and friends. For a real
 * instant (`2026-09-10T11:59:00Z`, e.g. a conference round's `instant`), plain
 * `new Date(...)` is correct and this would throw the time away.
 */
export function formatIsoDate(dateIso: string): string {
  if (!dateIso) return "";
  const [y, m, d] = dateIso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return dateIso;
  const date = new Date(y, m - 1, d);
  if (Number.isNaN(date.getTime())) return dateIso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Human label for the actionable deadline, e.g. "Application due Nov 12, 2026". */
export function deadlineLabel(kind: string, dateIso: string): string {
  if (!dateIso) return "";
  const when = formatIsoDate(dateIso) || dateIso;
  const label: Record<string, string> = {
    application: "Application due",
    abstract: "Abstract due",
    manuscript: "Full paper due",
    event: "Event",
  };
  return `${label[kind] ?? "Deadline"} ${when}`;
}

/**
 * A short noun for what a saved deadline is counting down to — "Abstract",
 * "Apply to Conference", "Full paper", "Event". Returns "" when the kind is
 * unknown so the caller can fall back to a bare countdown.
 */
export function deadlineKindLabel(kind: string, area: string): string {
  switch (kind) {
    case "abstract":
      return "Abstract";
    case "manuscript":
      return "Full paper";
    case "application":
      return area === "conference" ? "Apply to Conference" : "Apply";
    case "event":
      return "Event";
    default:
      return "";
  }
}

/**
 * A bookmark control that saves an item (paper, grant, conference, or
 * fellowship) to the caller's **personal** workspace, or — for a lab manager —
 * to one of their **labs'** shared saves.
 *
 * With no managed labs it is a plain personal toggle (unchanged). With one or
 * more managed labs it becomes a small dropdown: Personal plus each managed lab,
 * each showing a check when the item is already saved there. Selecting a row
 * toggles that scope. `savedLabs` is the list of managed-lab slugs already
 * holding the item (from the feed's `saved_labs`).
 *
 * `variant="icon"` renders a compact round trigger (used where space is tight);
 * the default renders the labelled pill used on the Saves page.
 */
export function SaveButton({
  contentId,
  saved,
  savedLabs = [],
  variant = "full",
}: {
  contentId: string;
  saved: boolean;
  savedLabs?: string[];
  variant?: "full" | "icon";
}) {
  const { save, unsave } = useSaveOpportunity();
  const labsQuery = useMyLabs();
  const managedLabs = React.useMemo(
    () => (labsQuery.data ?? []).filter(canManageLab),
    [labsQuery.data],
  );
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  const pending = save.isPending || unsave.isPending;
  const savedLabSet = React.useMemo(() => new Set(savedLabs), [savedLabs]);
  const anySaved = saved || savedLabs.length > 0;

  const toggleScope = (labSlug?: string) => {
    const already = labSlug ? savedLabSet.has(labSlug) : saved;
    if (already) {
      unsave.mutate({ contentId, labSlug });
      return;
    }
    save.mutate({ contentId, labSlug });
    if (labSlug) setOpen(false);
  };

  // No labs to save into → the original one-click personal toggle.
  if (managedLabs.length === 0) {
    return (
      <SaveTrigger
        variant={variant}
        active={saved}
        pending={pending}
        label={saved ? "Remove from your saves" : "Save for later"}
        onClick={() => toggleScope()}
      />
    );
  }

  return (
    <div ref={ref} className="relative inline-flex shrink-0">
      <SaveTrigger
        variant={variant}
        active={anySaved}
        pending={pending}
        hasCaret
        label="Choose where to save"
        onClick={() => setOpen((v) => !v)}
        expanded={open}
      />
      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-40 min-w-[220px] rounded-2xl border border-border bg-surface p-1.5 shadow-[var(--shadow)]"
        >
          <p className="px-2.5 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Save to
          </p>
          <SaveScopeItem
            label="Personal"
            checked={saved}
            disabled={pending}
            onSelect={() => toggleScope()}
          />
          {managedLabs.map((lab) => (
            <SaveScopeItem
              key={lab.slug}
              label={lab.name}
              checked={savedLabSet.has(lab.slug)}
              disabled={pending}
              onSelect={() => toggleScope(lab.slug)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The bell control that opens the deadline-reminder composer as a centered
 * popup. It sits to the left of the Save button on any dated opportunity (grant,
 * conference, fellowship). A personal reminder is a Discord DM; a lab reminder
 * posts to the channel chosen in the composer. Renders nothing when the item has
 * no dated deadline to count down to (papers, rolling calls), so no bell shows
 * where a reminder would be meaningless.
 *
 * `lockedLabSlug` pins the composer to a single lab — used from a lab's saved
 * area, where every reminder posts to that lab's channel.
 */
export function RemindButton({
  contentId,
  title,
  deadlines,
  lockedLabSlug,
}: {
  contentId: string;
  title: string;
  deadlines: DeadlineOption[];
  lockedLabSlug?: string;
}) {
  const [composing, setComposing] = React.useState(false);
  // Reminders need a paid plan and a synced Discord account (the lab's server, in
  // lab scope). One shared query answers for every bell on the page. The control
  // stays visible and clickable when locked — a missing button teaches nothing,
  // and the composer names exactly which of the two conditions is unmet.
  const access = useReminderAccess(lockedLabSlug);
  const locked = access.data ? !access.data.allowed : false;
  // Only *dated* deadlines are remindable — a rolling call has no date to count
  // down to, so the bell simply doesn't render for it.
  const datedDeadlines = React.useMemo(
    () => deadlines.filter((d) => d.due_date),
    [deadlines],
  );
  if (datedDeadlines.length === 0) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setComposing(true)}
        aria-label={
          locked
            ? `Reminders unavailable for ${title} — see what's needed`
            : `Set a reminder for ${title}`
        }
        title={
          locked
            ? access.data?.detail || "Reminders aren't available on your plan"
            : "Set a reminder"
        }
        // Blue bell — deliberately off the warm palette so the reminder action
        // reads as clearly distinct from the neighbouring Save control. Locked, it
        // drops to the neutral surface tone so it never reads as an active control.
        className={cn(
          "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          locked
            ? "border-border bg-surface text-[var(--text-secondary)] opacity-70 hover:opacity-100"
            : "border-transparent bg-[#3f6fa3] text-white hover:bg-[#345c85]",
        )}
      >
        <BellIcon size={14} aria-hidden="true" />
      </button>
      {composing ? (
        <ReminderComposer
          contentId={contentId}
          title={title}
          deadlines={datedDeadlines}
          onClose={() => setComposing(false)}
          lockedScope={lockedLabSlug ? "lab" : undefined}
          lockedLabSlug={lockedLabSlug}
        />
      ) : null}
    </>
  );
}

/** The button that opens the save menu (or toggles a personal save directly). */
function SaveTrigger({
  variant,
  active,
  pending,
  label,
  onClick,
  hasCaret = false,
  expanded,
}: {
  variant: "full" | "icon";
  active: boolean;
  pending: boolean;
  label: string;
  onClick: () => void;
  hasCaret?: boolean;
  expanded?: boolean;
}) {
  const shared = {
    onClick,
    disabled: pending,
    "aria-label": label,
    title: label,
    ...(hasCaret
      ? { "aria-haspopup": "menu" as const, "aria-expanded": expanded }
      : { "aria-pressed": active }),
  };

  if (variant === "icon") {
    const iconTone = active
      ? "border-[color-mix(in_srgb,var(--accent)_45%,transparent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-accent hover:bg-[color-mix(in_srgb,var(--accent)_24%,transparent)]"
      : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[color-mix(in_srgb,var(--accent)_45%,transparent)] hover:bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] hover:text-accent";
    return (
      <button
        type="button"
        {...shared}
        className={cn(
          "inline-flex h-8 shrink-0 items-center justify-center gap-0.5 rounded-full border transition-colors disabled:opacity-60",
          hasCaret ? "px-2" : "w-8",
          iconTone,
        )}
      >
        <BookmarkIcon size={14} aria-hidden="true" />
        {hasCaret ? <ChevronDownIcon size={12} aria-hidden="true" /> : null}
      </button>
    );
  }

  const tone = active
    ? {
        borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)",
        color: "var(--accent)",
      }
    : {
        borderColor: "var(--border)",
        backgroundColor: "var(--surface)",
        color: "var(--text-secondary)",
      };
  return (
    <button
      type="button"
      {...shared}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60"
      style={tone}
    >
      <BookmarkIcon size={13} aria-hidden="true" />
      {active ? "Saved" : "Save"}
      {hasCaret ? <ChevronDownIcon size={12} aria-hidden="true" /> : null}
    </button>
  );
}

/** One scope row in the save menu (personal or a lab), with a saved check. */
function SaveScopeItem({
  label,
  checked,
  disabled,
  onSelect,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitemcheckbox"
      aria-checked={checked}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-[13.5px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60",
        checked && "bg-surface-alt",
      )}
    >
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
          checked
            ? "border-accent bg-accent text-[#fffdf8]"
            : "border-border text-transparent",
        )}
      >
        <CheckIcon size={12} aria-hidden="true" />
      </span>
      <span className="flex-1 truncate text-[var(--text-primary)]">
        {label}
      </span>
    </button>
  );
}
