"use client";

import * as React from "react";

import { CloseIcon } from "@/components/portal/icons";
import { useDismissable } from "@/lib/portal/use-dismissable";
import { cn } from "@/lib/utils";

/**
 * A small, dependency-free "toggletip": a button that reveals a panel of
 * supplementary text on click or tap, and closes on an outside click, Escape,
 * or its own close button. Built directly on `useDismissable` — the same
 * open/close/dismiss primitive `SaveButton`'s lab-choice menu already uses —
 * rather than a hover-only CSS tooltip, because a hover target can never be
 * reached by keyboard or by touch, and `docs/styles.md` requires both
 * (WCAG 2.2 AA).
 *
 * The app has no Radix `Tooltip`/`Popover` installed (only `dialog`,
 * `dropdown-menu`, `label`, `select`, `separator`, `slot`, `tabs`, `toast` —
 * checked against `web/app/package.json`), so this is the shared foundation
 * every rank/tier/deadline hover in Phase 10 is built on instead of each one
 * hand-rolling its own dismiss logic.
 *
 * The panel deliberately carries no ARIA `role` — it holds static
 * explanatory text plus its own close button, nothing that needs a
 * `role="dialog"`'s focus trap. `aria-expanded` + `aria-controls` on the
 * trigger is the whole contract: a screen reader in browse mode meets the
 * panel immediately after the trigger in document order, and a keyboard user
 * reaches it by activating the trigger with Enter/Space (free from using a
 * real `<button>`) and dismisses it with Escape.
 */
export function InfoPopover({
  trigger,
  triggerLabel,
  triggerClassName,
  triggerStyle,
  children,
  align = "start",
  panelClassName,
}: {
  /** The trigger's visible content — a badge pill, an icon + text line. */
  trigger: React.ReactNode;
  /** The trigger button's accessible name, read whether or not `trigger`
   * itself carries visible text (e.g. an icon-only pill). */
  triggerLabel: string;
  /** Full className for the trigger `<button>` — the caller's own pill/line
   * styling. Defaults to a bare, focus-ring-only wrapper. */
  triggerClassName?: string;
  /** Inline style for the trigger `<button>` — for `color-mix()` tokens the
   * same idiom as `EligibilityBadge`/`ClusterBadge` needs, which Tailwind's
   * static classes can't express. */
  triggerStyle?: React.CSSProperties;
  /** The panel's content. Keep it short — this is a hover explanation, not a
   * secondary page. */
  children: React.ReactNode;
  /** Which side of the trigger the panel's edge aligns to. */
  align?: "start" | "end";
  panelClassName?: string;
}) {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const panelId = React.useId();
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const wasOpenRef = React.useRef(false);

  // The panel (including its own close button) unmounts the instant `open`
  // goes false. When the close button itself held focus, React removes it
  // from the DOM before the browser has anywhere else to put focus, so focus
  // silently falls to <body> — a keyboard user's next Tab then restarts from
  // the top of the page instead of continuing from this control. Detect that
  // exact case (focus was inside this popover, and is now nowhere) and hand
  // it back to the trigger, which is the one element guaranteed to still be
  // mounted. An outside click or a click on another focusable element never
  // trips this: activeElement lands on that element, not <body>, so this
  // never fights a reader's own navigation.
  React.useEffect(() => {
    if (wasOpenRef.current && !open && document.activeElement === document.body) {
      triggerRef.current?.focus();
    }
    wasOpenRef.current = open;
  }, [open]);

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={triggerLabel}
        style={triggerStyle}
        className={cn(
          "text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          triggerClassName,
        )}
      >
        {trigger}
      </button>
      {open ? (
        <div
          id={panelId}
          className={cn(
            "absolute top-[calc(100%+6px)] z-40 w-72 max-w-[calc(100vw-2rem)] rounded-2xl border border-border bg-surface p-3.5 text-xs leading-relaxed text-[var(--text-secondary)] shadow-[var(--shadow)]",
            align === "end" ? "right-0" : "left-0",
            panelClassName,
          )}
        >
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="absolute right-2 top-2 inline-flex h-6 w-6 items-center justify-center rounded-full text-[var(--text-muted)] hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <CloseIcon size={11} aria-hidden="true" />
          </button>
          <div className="pr-5">{children}</div>
        </div>
      ) : null}
    </div>
  );
}
