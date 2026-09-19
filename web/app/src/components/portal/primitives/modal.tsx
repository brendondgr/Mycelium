"use client";

import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

/**
 * A centered dialog over a dimmed, blurred page — rendered into `document.body`
 * rather than where it is written.
 *
 * The portal is not tidiness, it is the fix for a real bug. `position: fixed`
 * resolves against the viewport *only* while no ancestor establishes a
 * containing block, and any ancestor with a transform other than `none` does.
 * Every feed card is wrapped by `RevealOnScroll`, whose `portal-fade-up`
 * animation is declared `animation-fill-mode: both`, so the wrapper keeps
 * `transform: translateY(0)` — a real matrix, not `none` — permanently after its
 * entrance plays. A dialog opened from a card was therefore laid out against
 * *that card*: it appeared inside the container it was launched from, its
 * backdrop covered only the card, and every control outside stayed clickable and
 * tabbable. Portalling to `body` escapes every transformed ancestor by
 * construction, so no future decorative animation can reintroduce it.
 *
 * What this owns, so no caller re-implements it slightly differently:
 * centering, the dimmed + blurred backdrop, Escape, click-outside, body scroll
 * lock, an initial focus, a focus trap, and focus restoration to whatever opened
 * it. Anything a keyboard or screen-reader user needs is here rather than
 * optional.
 */
export function Modal({
  onClose,
  label,
  children,
  className,
  width = "md",
}: {
  onClose: () => void;
  /** The dialog's accessible name — what a screen reader announces on open. */
  label: string;
  children: React.ReactNode;
  className?: string;
  /** `side` is a full-height panel on the right on desktop and the whole
   * screen on a phone — for work that should keep the page it came from in
   * view (the collaborator search). */
  width?: "md" | "lg" | "side";
}) {
  const panelRef = React.useRef<HTMLDivElement | null>(null);
  // Captured on mount, before the dialog steals focus, so it can be handed back.
  const openerRef = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    openerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      // Restore focus rather than dropping it on `<body>`, where the next Tab
      // would restart from the top of the page instead of the control that
      // opened this.
      openerRef.current?.focus?.();
    };
  }, []);

  React.useEffect(() => {
    // Move focus in once the panel exists. Preferring the first focusable child
    // over the panel itself means the dialog opens *on* a control, so the first
    // Tab moves to the second one rather than into the dialog.
    const panel = panelRef.current;
    if (!panel) return;
    const first = focusable(panel)[0];
    (first ?? panel).focus({ preventScroll: true });
  }, []);

  // Focus can fall out of the dialog without the user leaving it — a button
  // that disables itself while it works (the collaborator search's Run) drops
  // focus to <body>. The panel's own handler never sees keys pressed then, so
  // Escape did nothing and Tab walked into the page behind. Catch both at the
  // document: Escape closes, Tab brings focus back inside.
  const onCloseRef = React.useRef(onClose);
  React.useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  React.useEffect(() => {
    const onDocumentKey = (event: KeyboardEvent) => {
      const panel = panelRef.current;
      // Only when focus has fallen to the page itself — never when it is in
      // another dialog stacked above this one, whose keys are its own.
      if (!panel || event.target !== document.body) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
      } else if (event.key === "Tab") {
        event.preventDefault();
        (focusable(panel)[0] ?? panel).focus();
      }
    };
    document.addEventListener("keydown", onDocumentKey);
    return () => document.removeEventListener("keydown", onDocumentKey);
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    // The trap. Without it Tab walks straight out of the dialog and into the
    // page behind it, which is still rendered and still focusable — the same
    // "everything behind stays reachable" failure the portal fixes visually.
    const panel = panelRef.current;
    if (!panel) return;
    const items = focusable(panel);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === panel)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  // No "have I hydrated yet" dance: a Modal is only ever rendered in response to
  // a click, so it never exists during the server render and there is nothing to
  // hydrate. Gating on state instead would cost a frame and make the dialog
  // visibly appear late.
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-[100] flex bg-[color-mix(in_srgb,var(--text-primary)_38%,transparent)] backdrop-blur-sm",
        width === "side"
          ? "items-stretch justify-end"
          : "items-center justify-center overflow-y-auto p-4",
      )}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onMouseDown={(event) => {
        // `mousedown`, not `click`: a click whose press started *inside* the
        // panel and released on the backdrop (a drag while selecting text)
        // targets the backdrop and would otherwise close the dialog mid-edit.
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={onKeyDown}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          "w-full bg-surface shadow-[var(--shadow)] focus:outline-none",
          "motion-safe:animate-[portal-fade-up_0.18s_cubic-bezier(0.22,0.61,0.36,1)_both]",
          width === "side"
            ? "flex h-full max-w-xl flex-col overflow-y-auto border-border sm:border-l"
            : cn(
                "my-auto overflow-hidden rounded-2xl border border-border",
                width === "lg" ? "max-w-2xl" : "max-w-md",
              ),
          className,
        )}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

/**
 * The dialog's own header: eyebrow, title, and a close control.
 *
 * Shared so the two reminder dialogs cannot drift apart on spacing, and so the
 * close button is never the accidental first tab stop — it is rendered after the
 * heading in DOM order, which is also its reading order.
 */
export function ModalHeader({
  eyebrow,
  title,
  onClose,
}: {
  eyebrow: string;
  title: string;
  onClose: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[var(--divider)] px-5 py-3.5">
      <div className="min-w-0">
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {eyebrow}
        </p>
        <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">
          {title}
        </p>
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="shrink-0 rounded-full p-1 text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <CloseGlyph />
      </button>
    </div>
  );
}

/** Inlined rather than imported so this primitive has no icon dependency. */
function CloseGlyph() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
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

/** Focusable descendants in DOM order, skipping anything currently hidden. */
function focusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}
