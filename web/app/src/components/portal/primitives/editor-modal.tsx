"use client";

import * as React from "react";
import { createPortal } from "react-dom";

import { CloseIcon } from "@/components/portal/icons";
import { cn } from "@/lib/utils";

/** One tab in an `EditorModal` — a stable id, its rail label, and its panel. */
export type EditorTab = {
  id: string;
  label: string;
  /** Optional one-line hint shown under the label in the rail. */
  hint?: string;
  content: React.ReactNode;
};

type EditorModalProps = {
  /** Small uppercase label above the title ("Lab profile", "Your profile"). */
  eyebrow?: string;
  title: string;
  subtitle?: string;
  tabs: EditorTab[];
  activeTab: string;
  onTabChange: (id: string) => void;
  /**
   * An `EditorSection` `anchorId` to scroll to once, on open. A tab here is a
   * long page, so a caller that meant "edit the eligibility answers" needs to
   * land on that block rather than at the top of the tab holding it.
   */
  initialAnchor?: string | null;
  onClose: () => void;
  onSave: () => void;
  saving?: boolean;
  saveLabel?: string;
  /** Blocks the save button with an explanation left of the footer buttons. */
  saveDisabledReason?: string | null;
  error?: string | null;
};

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-5 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/**
 * The one editing surface the workspace uses: a **full-screen** page with a tab
 * rail down the left, one scrolling panel, and a fixed Cancel/Save footer.
 *
 * Editing a profile — personal or lab — used to mean being sent back through the
 * onboarding flow, which is a first-run *narrative* (verify, import, review, one
 * step at a time) and the wrong shape for "change the cadence". This is the
 * opposite: everything is on screen at once, reachable in one click, and saved in
 * one action.
 *
 * It takes the whole viewport rather than sitting in a centred window. Editing a
 * profile is a task, not a confirmation: the reader is reading long prose, drag-
 * sorting themes and comparing fields that used to be a tab apart, and a card-
 * sized box floating over the page it came from both cramped that work and read
 * as an interruption of it. There is nothing behind it worth keeping in view, so
 * nothing is kept in view — hence no backdrop and no click-outside either.
 *
 * It renders through a portal into `document.body`. `position: fixed` resolves
 * against the viewport only while no ancestor establishes a containing block,
 * and any ancestor with a transform does — the portal escapes every one of them
 * by construction, so a decorative animation somewhere up the tree can never
 * shrink this back down to the card it was opened from.
 *
 * Every panel stays mounted (inactive ones are `hidden`), so switching tabs never
 * loses in-progress edits and a long form's scroll position survives a detour.
 */
export function EditorModal({
  eyebrow,
  title,
  subtitle,
  tabs,
  activeTab,
  onTabChange,
  initialAnchor = null,
  onClose,
  onSave,
  saving = false,
  saveLabel = "Save changes",
  saveDisabledReason = null,
  error = null,
}: EditorModalProps) {
  const titleId = React.useId();
  const panelRef = React.useRef<HTMLDivElement>(null);
  const closeRef = React.useRef<HTMLButtonElement>(null);
  const tabRefs = React.useRef<Record<string, HTMLButtonElement | null>>({});
  const dialogRef = React.useRef<HTMLDivElement>(null);
  // Captured on mount, before the dialog steals focus, so it can be handed back.
  const openerRef = React.useRef<HTMLElement | null>(null);
  // Suppresses the scroll-to-top that a tab change normally does, for the one
  // render where the caller's anchor is being honoured instead.
  const anchorPending = React.useRef(Boolean(initialAnchor));

  const current = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  // Escape closes; the page behind must not scroll while the dialog owns the
  // screen. Both are undone on unmount so a re-open starts clean.
  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  // Open with focus inside the dialog rather than wherever the trigger was, so a
  // keyboard user lands in the new context instead of behind it — and hand focus
  // back to whatever opened it on the way out, rather than dropping it on
  // `<body>` where the next Tab restarts from the top of the page.
  React.useEffect(() => {
    openerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    closeRef.current?.focus();
    return () => {
      openerRef.current?.focus?.();
    };
  }, []);

  // Changing tab scrolls the panel back to the top — a tab is a new surface, not
  // a continuation of the previous one. The exception is the first paint of an
  // anchored open, which is deliberately landing part-way down.
  React.useEffect(() => {
    if (anchorPending.current) {
      return;
    }
    panelRef.current?.scrollTo({ top: 0 });
  }, [activeTab]);

  // Honour the caller's anchor once the panel is in the document. Every tab is
  // mounted, so the same anchor id could exist on an inactive one; `offsetParent`
  // is null inside a `hidden` panel, which is what picks out the visible match.
  React.useEffect(() => {
    if (!initialAnchor) {
      return;
    }
    const panel = panelRef.current;
    const target = Array.from(
      panel?.querySelectorAll<HTMLElement>(
        `[data-editor-anchor="${initialAnchor}"]`,
      ) ?? [],
    ).find((element) => element.offsetParent !== null);
    if (panel && target) {
      // Measured, not `offsetTop`: the panel is not a positioned ancestor, so
      // `offsetTop` would be read against the dialog and land the reader a
      // header's height off.
      const delta =
        target.getBoundingClientRect().top - panel.getBoundingClientRect().top;
      panel.scrollTo({ top: Math.max(0, panel.scrollTop + delta - 12) });
    }
    anchorPending.current = false;
  }, [initialAnchor]);

  /**
   * The focus trap. The dialog now covers the viewport, so without it Tab walks
   * out of the editor and onto the page behind — which is still rendered, still
   * focusable, and no longer visible at all.
   */
  function onDialogKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") {
      return;
    }
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    const items = focusable(dialog);
    if (items.length === 0) {
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /** Roving arrow-key navigation across the rail, per the tabs pattern. */
  function onTabKeyDown(event: React.KeyboardEvent, index: number) {
    const forward = event.key === "ArrowDown" || event.key === "ArrowRight";
    const back = event.key === "ArrowUp" || event.key === "ArrowLeft";
    if (!forward && !back && event.key !== "Home" && event.key !== "End") {
      return;
    }
    event.preventDefault();
    const last = tabs.length - 1;
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? last
          : forward
            ? (index + 1) % tabs.length
            : (index - 1 + tabs.length) % tabs.length;
    const target = tabs[next];
    anchorPending.current = false;
    onTabChange(target.id);
    tabRefs.current[target.id]?.focus();
  }

  // No "have I hydrated yet" dance: this dialog is only ever rendered in
  // response to a click, so it never exists during the server render and there
  // is nothing to hydrate. Gating on state instead would cost a frame and make
  // the editor visibly appear late.
  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onKeyDown={onDialogKeyDown}
      className="fixed inset-0 z-50 flex flex-col bg-surface"
    >
      {/* Header */}
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--divider)] px-5 py-4 sm:px-8">
        <div className="min-w-0">
          {eyebrow ? (
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--brand-primary-hover)]">
              {eyebrow}
            </p>
          ) : null}
          <h2
            id={titleId}
            className="truncate font-serif text-[22px] font-semibold leading-tight text-[var(--text-primary)]"
          >
            {title}
          </h2>
          {subtitle ? (
            <p className="mt-1 text-[13px] leading-5 text-[var(--text-secondary)]">
              {subtitle}
            </p>
          ) : null}
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close editor"
          className="shrink-0 rounded-full border border-border bg-surface p-2 text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <CloseIcon size={15} />
        </button>
      </div>

      {/* Rail + panel. The rail is a column beside the panel from `sm` up and a
          horizontal scroller above it on a phone, where a column would eat the
          width the form needs. */}
      <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
        <div
          role="tablist"
          aria-orientation="vertical"
          aria-label={`${title} sections`}
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-[var(--divider)] bg-surface-alt px-3 py-2.5 sm:w-[244px] sm:flex-col sm:overflow-x-visible sm:overflow-y-auto sm:border-b-0 sm:border-r sm:px-3 sm:py-5"
        >
          {tabs.map((tab, index) => {
            const selected = tab.id === current?.id;
            return (
              <button
                key={tab.id}
                ref={(element) => {
                  tabRefs.current[tab.id] = element;
                }}
                type="button"
                role="tab"
                id={`${titleId}-tab-${tab.id}`}
                aria-selected={selected}
                aria-controls={`${titleId}-panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => {
                  anchorPending.current = false;
                  onTabChange(tab.id);
                }}
                onKeyDown={(event) => onTabKeyDown(event, index)}
                className={cn(
                  "shrink-0 whitespace-nowrap rounded-xl px-3.5 py-2 text-left text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:whitespace-normal",
                  selected
                    ? "bg-surface text-[var(--text-primary)] shadow-[var(--shadow)]"
                    : "text-[var(--text-secondary)] hover:bg-surface",
                )}
              >
                {tab.label}
                {tab.hint ? (
                  <span className="mt-0.5 hidden text-[11.5px] font-normal leading-4 text-[var(--text-muted)] sm:block">
                    {tab.hint}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        {/* One readable column, centred. Full-bleed buys the height a long tab
            needs; it does not buy 2000px-wide paragraphs and inputs. */}
        <div ref={panelRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-10 sm:py-8">
          <div className="mx-auto w-full max-w-[880px]">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                role="tabpanel"
                id={`${titleId}-panel-${tab.id}`}
                aria-labelledby={`${titleId}-tab-${tab.id}`}
                hidden={tab.id !== current?.id}
                tabIndex={0}
                className="focus-visible:outline-none"
              >
                {tab.content}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-[var(--divider)] px-5 py-3.5 sm:px-8">
        <p
          className={cn(
            "min-w-0 flex-1 text-[12.5px]",
            error ? "text-clay" : "text-[var(--text-secondary)]",
          )}
          role={error ? "alert" : undefined}
        >
          {error ?? saveDisabledReason ?? ""}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            className={GHOST_BUTTON}
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="button"
            className={PRIMARY_BUTTON}
            onClick={onSave}
            disabled={saving || Boolean(saveDisabledReason)}
          >
            {saving ? "Saving…" : saveLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** A labelled block inside an editor panel. */
export function EditorField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-[var(--text-primary)]">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11.5px] text-[var(--text-muted)]">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

/**
 * The heading that opens a group of fields within one tab panel.
 *
 * A tab holds several of these now rather than one, so consecutive sections are
 * ruled off from each other — without the rule, a merged tab reads as one
 * undifferentiated column of inputs. `anchorId` is what `EditorModal`'s
 * `initialAnchor` scrolls to.
 */
export function EditorSection({
  title,
  description,
  anchorId,
  children,
}: {
  title: string;
  description?: string;
  anchorId?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-editor-anchor={anchorId}
      className="mt-8 border-t border-[var(--divider)] pt-8 first:mt-0 first:border-t-0 first:pt-0"
    >
      <h3 className="font-serif text-[17px] font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      {description ? (
        <p className="mt-1 text-[13px] leading-5 text-[var(--text-secondary)]">
          {description}
        </p>
      ) : null}
      <div className="mt-3.5 space-y-4">{children}</div>
    </section>
  );
}

/** The on/off row used by both editors' "signals to surface" lists. */
export function EditorToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <div className="flex items-center gap-4 border-b border-[var(--divider)] py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="m-0 text-[13.5px] font-semibold text-[var(--text-primary)]">
          {label}
        </p>
        {description ? (
          <p className="m-0 text-[12px] text-[var(--text-muted)]">{description}</p>
        ) : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={onChange}
        className={cn(
          "relative h-6 w-11 flex-none rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          checked ? "bg-primary" : "bg-border",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-surface shadow transition-all",
            checked ? "left-[22px]" : "left-0.5",
          )}
        />
      </button>
    </div>
  );
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Focusable descendants in DOM order, skipping anything currently hidden — which
 * is how the inactive tab panels, mounted but `hidden`, stay out of the cycle.
 *
 * `tabIndex` is re-checked rather than left to the selector: the rail uses a
 * roving tabindex, so its unselected buttons match `button:not([disabled])`
 * while Tab will never reach them. Leaving them in would put the cycle's real
 * first stop in the middle of the list and let Shift+Tab slip past the trap.
 */
function focusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) =>
      element.tabIndex >= 0 &&
      (element.offsetParent !== null || element === document.activeElement),
  );
}
