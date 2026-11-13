"use client";

import * as React from "react";

import {
  BellIcon,
  BookmarkIcon,
  CheckIcon,
  ChevronDownIcon,
  CloseIcon,
  EyeOffIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import {
  DeadlineMenu,
  type ExtraDeadline,
} from "@/components/portal/primitives/deadline-list";
import { ReminderComposer } from "@/components/portal/reminder-composer";
import { usePersonalOnly } from "@/components/portal/personal-only-scope";
import {
  useIgnoreItem,
  useMyLabs,
  useReminderAccess,
  useReminderMutations,
  useSaveOpportunity,
} from "@/lib/portal/hooks";
import { formatIsoDate } from "@/lib/portal/dates";
import { useDismissable } from "@/lib/portal/use-dismissable";
import type { DeadlineOption } from "@/lib/portal/types";
import { cn } from "@/lib/utils";
import { CAPABILITY, holding } from "@/lib/portal/capabilities";


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
 * Re-exported so the cards keep one import for their formatting helpers. The
 * implementation lives in `lib/portal/dates` — see that module for why.
 */
export { formatIsoDate };

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

/* ----------------------------------------------------------------------- */
/* The card's tools: ignore, remind, bookmark — and the way back             */
/* ----------------------------------------------------------------------- */

/** How long the undo popup stays up before the card moves on without it. */
const UNDO_TIMEOUT_MS = 7000;

/**
 * One completed action a card is offering to reverse.
 *
 * Every tool reports its own, because only the tool knows what it did: the
 * bookmark knows *which* scope it saved to, the bell knows which reminder row
 * the server created, ignore knows the item it hid.
 */
export type UndoAction = {
  /** Past tense, one short sentence: "Saved to your saves." */
  message: string;
  undo: () => void;
  /** Run when the popup goes away *without* being undone (ignore collapses). */
  onExpire?: () => void;
};

/**
 * Holds the card's single pending undo offer, and expires it on a timer.
 *
 * One at a time by design: a card is one row in a feed, and stacking two
 * popups in the middle of it would cover the thing they are talking about.
 * A newly raised action replaces the previous one and the earlier one's
 * `onExpire` is deliberately *not* run — it was superseded, not ignored.
 */
export function useCardUndo() {
  const [action, setAction] = React.useState<UndoAction | null>(null);

  React.useEffect(() => {
    if (!action) return;
    const timer = window.setTimeout(() => {
      setAction(null);
      action.onExpire?.();
    }, UNDO_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [action]);

  // The mutation fires from the callback, never from inside a state updater:
  // React may invoke an updater more than once (it does in development's
  // StrictMode), and an undo that ran twice would re-save what it just removed.
  const raise = React.useCallback((next: UndoAction) => setAction(next), []);
  const undo = React.useCallback(() => {
    if (!action) return;
    setAction(null);
    action.undo();
  }, [action]);
  const dismiss = React.useCallback(() => {
    if (!action) return;
    setAction(null);
    action.onExpire?.();
  }, [action]);

  return { action, raise, undo, dismiss };
}

/**
 * The undo popup: what just happened, and the way back, floated in the centre
 * of the card the action was taken on.
 *
 * Centred rather than anchored to the control, because the three tools sit in
 * a 32px row in the card's corner and a popup hanging off any one of them
 * would leave the reader hunting for which. `role="status"` so the change is
 * announced, not only seen — and the whole thing is keyboard reachable, since
 * an undo that only a mouse can reach is not an undo.
 *
 * It expires on its own (see {@link UNDO_TIMEOUT_MS}); the card stays put.
 */
export function UndoPopup({
  action,
  onUndo,
  onDismiss,
}: {
  action: UndoAction | null;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  if (!action) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center p-4">
      <div
        role="status"
        className="pointer-events-auto flex max-w-full items-center gap-2.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3.5 py-2 shadow-[var(--shadow)]"
      >
        <span className="min-w-0 truncate text-[13px] font-medium text-[var(--text-primary)]">
          {action.message}
        </span>
        <button
          type="button"
          onClick={onUndo}
          className="shrink-0 rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:border-[color-mix(in_srgb,var(--accent)_45%,transparent)] hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Undo
        </button>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 rounded-full p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <CloseIcon size={12} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/**
 * The block in a matched card's top-right corner: the three tools in one row —
 * **ignore, reminder, bookmark**, in that order — with the card's **Deadlines**
 * control directly beneath them, spanning their combined width.
 *
 * Each tool carries its own colour (ignore terracotta, reminder blue, bookmark
 * gold) but wears none of it at rest. A row of three saturated icons on every
 * card in a feed of twenty-five reads as an alarm; the colour is there to
 * confirm what you are about to press, so it arrives on hover and focus. The
 * one exception is a bookmark already holding a save, which stays gold: that is
 * state, not decoration, and hiding it would lose the answer to "did I save
 * this?".
 *
 * The bar owns the card's undo popup and hands `onUndo` to all three tools, so
 * every action taken here can be taken back from one place. Ignoring is the
 * only one that changes the card: it waits for the popup to expire and then
 * calls `onIgnored`, which collapses the row into {@link IgnoredStrip}.
 *
 * `deadlines` may be empty (a rolling call, an undated listing) — the bell and
 * the Deadlines control both render nothing rather than an inert stub.
 */
export function CardActionBar({
  contentId,
  title,
  deadlines,
  extraDeadlines,
  deadlineFootnote,
  saved,
  savedLabs,
  remindLabSlug,
  ignorable = false,
  onIgnored,
}: {
  contentId: string;
  title: string;
  deadlines: DeadlineOption[];
  /** Display-only deadline rows (passed rounds, later grant rounds). */
  extraDeadlines?: ExtraDeadline[];
  /** Extra context under the deadline list (a letter of intent, a moved date). */
  deadlineFootnote?: React.ReactNode;
  saved: boolean;
  savedLabs?: string[];
  /** Set from a lab's Saves area so reminders post to that lab's channel. */
  remindLabSlug?: string;
  ignorable?: boolean;
  onIgnored?: () => void;
}) {
  const undo = useCardUndo();
  return (
    <>
      {/* The column was 6.75rem — exactly the three 2rem tools plus their two
          0.375rem gaps — which sized it from the tool row and left the Deadlines
          control beneath them to truncate whatever date it carried ("Sep 10, …").
          A date is the whole point of that control, so the column is sized from
          the wider of the two things in it instead: 8.75rem fits a full
          "Sep 10, 2026" with the calendar icon and chevron either side, and the
          tools stay flush right, so the row still reads as one block. */}
      <div className="flex w-[8.75rem] shrink-0 flex-col items-end">
        <div className="flex items-center justify-end gap-1.5">
          {ignorable ? (
            <IgnoreButton
              contentId={contentId}
              title={title}
              onIgnored={onIgnored}
              onUndo={undo.raise}
            />
          ) : null}
          <RemindButton
            contentId={contentId}
            title={title}
            deadlines={deadlines}
            lockedLabSlug={remindLabSlug}
            onUndo={undo.raise}
          />
          <SaveButton
            contentId={contentId}
            saved={saved}
            savedLabs={savedLabs}
            variant="icon"
            onUndo={undo.raise}
          />
        </div>
        <DeadlineMenu
          contentId={contentId}
          title={title}
          deadlines={deadlines}
          extraDeadlines={extraDeadlines}
          footnote={deadlineFootnote}
          lockedLabSlug={remindLabSlug}
        />
      </div>
      <UndoPopup
        action={undo.action}
        onUndo={undo.undo}
        onDismiss={undo.dismiss}
      />
    </>
  );
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
 * the default renders the labelled pill used on the Saves page. Either way the
 * control is uncoloured until it is hovered, focused, or actually holding a
 * save — see `CardActionBar` for why the card's three tools rest neutral.
 *
 * `onUndo` is how the card offers the way back: every completed toggle reports
 * what it did and how to reverse it, and the card raises that as a popup.
 */
export function SaveButton({
  contentId,
  saved,
  savedLabs = [],
  variant = "full",
  onUndo,
}: {
  contentId: string;
  saved: boolean;
  savedLabs?: string[];
  variant?: "full" | "icon";
  onUndo?: (action: UndoAction) => void;
}) {
  const { save, unsave } = useSaveOpportunity();
  const labsQuery = useMyLabs();
  // Inside an invite-only project a save stays personal: a lab save would show
  // the whole lab what the project is looking at.
  const personalOnly = usePersonalOnly();
  const managedLabs = React.useMemo(
    () =>
      personalOnly ? [] : (labsQuery.data ?? []).filter(holding(CAPABILITY.PROFILE_EDIT)),
    [labsQuery.data, personalOnly],
  );
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  const pending = save.isPending || unsave.isPending;
  const savedLabSet = React.useMemo(() => new Set(savedLabs), [savedLabs]);
  const anySaved = saved || savedLabs.length > 0;

  const scopeName = (labSlug?: string) =>
    labSlug
      ? managedLabs.find((lab) => lab.slug === labSlug)?.name || "the lab"
      : "your saves";

  const toggleScope = (labSlug?: string) => {
    const already = labSlug ? savedLabSet.has(labSlug) : saved;
    const where = scopeName(labSlug);
    if (already) {
      unsave.mutate(
        { contentId, labSlug },
        {
          onSuccess: () =>
            onUndo?.({
              message: `Removed from ${where}.`,
              undo: () => save.mutate({ contentId, labSlug }),
            }),
        },
      );
      return;
    }
    save.mutate(
      { contentId, labSlug },
      {
        onSuccess: () =>
          onUndo?.({
            message: `Saved to ${where}.`,
            undo: () => unsave.mutate({ contentId, labSlug }),
          }),
      },
    );
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
  onUndo,
}: {
  contentId: string;
  title: string;
  deadlines: DeadlineOption[];
  lockedLabSlug?: string;
  /** Report a created reminder so the card can offer to take it back. */
  onUndo?: (action: UndoAction) => void;
}) {
  const [composing, setComposing] = React.useState(false);
  // Undo purges rather than cancels: the reader is saying "I didn't mean to
  // make this", and a soft-cancelled row would leave a reminder they never
  // wanted sitting on the reminders page explaining itself.
  const { remove } = useReminderMutations();
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
            : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[#3f6fa3] hover:bg-[#3f6fa3] hover:text-white focus-visible:border-[#3f6fa3] focus-visible:bg-[#3f6fa3] focus-visible:text-white",
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
          onCreated={(reminder) =>
            onUndo?.({
              message: "Reminder set.",
              undo: () => remove.mutate({ id: reminder.id, purge: true }),
            })
          }
          lockedScope={lockedLabSlug ? "lab" : undefined}
          lockedLabSlug={lockedLabSlug}
        />
      ) : null}
    </>
  );
}

/**
 * The manual **ignore** control: "I've looked at this, stop showing it to me."
 *
 * It leads the card's three tools — ignore, reminder, bookmark — sharing their
 * round 32px shape and their resting tone: a plain surface pill that only takes
 * its own colour (here a destructive terracotta) on hover or focus, so a feed of
 * twenty-five cards does not read as a wall of alarms. It is always mounted and
 * always in the tab order: a control that appears on hover is unreachable by
 * touch and invisible to a screen reader.
 *
 * `onIgnored` lets the card collapse itself into an undo strip rather than
 * vanishing — see `IgnoredStrip`. Without it the card simply disappears on the
 * next refetch, which is the right behaviour on surfaces (like search) that keep
 * showing the item anyway.
 *
 * `ignored` renders the control as a toggle that puts the item **back**. Feeds
 * never pass it — an ignored item is not in a feed — but search does, since a
 * search deliberately still returns what you dismissed.
 */
export function IgnoreButton({
  contentId,
  title,
  ignored = false,
  onIgnored,
  onUndo,
}: {
  contentId: string;
  title: string;
  ignored?: boolean;
  onIgnored?: () => void;
  /**
   * Raise the card's undo popup. When it is wired, the collapse waits for the
   * popup to go away — the card stays readable while the offer to take it back
   * is on screen, and only then folds into {@link IgnoredStrip}.
   */
  onUndo?: (action: UndoAction) => void;
}) {
  const { ignore, restore } = useIgnoreItem();
  const pending = ignore.isPending || restore.isPending;
  const label = ignored ? `Stop ignoring ${title}` : `Ignore ${title}`;

  const onClick = () => {
    if (ignored) {
      restore.mutate({ contentId });
      return;
    }
    ignore.mutate({ contentId });
    if (onUndo) {
      onUndo({
        message: "Ignored — you won't see this again.",
        undo: () => restore.mutate({ contentId }),
        onExpire: onIgnored,
      });
      return;
    }
    onIgnored?.();
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      aria-label={label}
      aria-pressed={ignored}
      title={
        ignored
          ? "Show this again"
          : "Ignore — stop showing this to me"
      }
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-50",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        ignored
          ? "border-[color-mix(in_srgb,var(--destructive)_45%,transparent)] bg-[color-mix(in_srgb,var(--destructive)_12%,transparent)] text-[var(--destructive)]"
          : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[color-mix(in_srgb,var(--destructive)_50%,transparent)] hover:bg-[color-mix(in_srgb,var(--destructive)_12%,transparent)] hover:text-[var(--destructive)] focus-visible:border-[color-mix(in_srgb,var(--destructive)_50%,transparent)] focus-visible:text-[var(--destructive)]",
      )}
    >
      <EyeOffIcon size={14} aria-hidden="true" />
    </button>
  );
}

/**
 * What a card collapses to the moment it is ignored: one line saying so, with
 * the way back. A card that silently vanished would leave the reader unsure
 * whether they hit the right control, and no way to correct a misfire until the
 * Ignored view. The strip lives until the next refetch drops the item.
 *
 * `role="status"` so the change is announced rather than only seen.
 */
export function IgnoredStrip({
  contentId,
  title,
  onRestored,
}: {
  contentId: string;
  title: string;
  onRestored: () => void;
}) {
  const { restore } = useIgnoreItem();
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 rounded-2xl border border-dashed border-border bg-[var(--surface)] px-4 py-3"
    >
      <p className="min-w-0 truncate text-sm text-[var(--text-secondary)]">
        Ignored <span className="font-medium">{title}</span>. You won&apos;t see
        it again.
      </p>
      <button
        type="button"
        disabled={restore.isPending}
        onClick={() => {
          restore.mutate({ contentId });
          onRestored();
        }}
        className="shrink-0 rounded-full border border-border px-3 py-1 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:border-[color-mix(in_srgb,var(--accent)_45%,transparent)] hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
      >
        Undo
      </button>
    </div>
  );
}

/**
 * Wraps one feed card so ignoring it collapses the card in place into
 * {@link IgnoredStrip} instead of leaving a gap. Every feed uses this rather
 * than each card owning the state, so all four areas behave identically.
 *
 * State is local and deliberately not reset by a refetch: once the server drops
 * the item from the feed, the whole wrapper unmounts with it.
 */
export function IgnorableCard({
  contentId,
  title,
  children,
}: {
  contentId: string;
  title: string;
  children: (props: { onIgnored: () => void }) => React.ReactNode;
}) {
  const [ignored, setIgnored] = React.useState(false);
  if (ignored) {
    return (
      <IgnoredStrip
        contentId={contentId}
        title={title}
        onRestored={() => setIgnored(false)}
      />
    );
  }
  return <>{children({ onIgnored: () => setIgnored(true) })}</>;
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
