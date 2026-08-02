"use client";

import * as React from "react";

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
 * The one editing surface the workspace uses: a near-full-page dialog with a tab
 * rail down the left, one scrolling panel, and a fixed Cancel/Save footer.
 *
 * Editing a profile — personal or lab — used to mean being sent back through the
 * onboarding flow, which is a first-run *narrative* (verify, import, review, one
 * step at a time) and the wrong shape for "change the cadence". This is the
 * opposite: everything is on screen at once, reachable in one click, and saved in
 * one action.
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
  // keyboard user lands in the new context instead of behind it.
  React.useEffect(() => {
    closeRef.current?.focus();
  }, []);

  // Changing tab scrolls the panel back to the top — a tab is a new surface, not
  // a continuation of the previous one.
  React.useEffect(() => {
    panelRef.current?.scrollTo({ top: 0 });
  }, [activeTab]);

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
    onTabChange(target.id);
    tabRefs.current[target.id]?.focus();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--text-primary)_38%,transparent)] p-0 backdrop-blur-sm sm:p-5"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex h-full w-full flex-col overflow-hidden border-border bg-surface shadow-[var(--shadow)] sm:h-[min(92vh,880px)] sm:max-w-5xl sm:rounded-2xl sm:border"
        onMouseDown={(event) => event.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--divider)] px-5 py-4 sm:px-7">
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
            className="flex shrink-0 gap-1 overflow-x-auto border-b border-[var(--divider)] px-3 py-2.5 sm:w-[212px] sm:flex-col sm:overflow-x-visible sm:overflow-y-auto sm:border-b-0 sm:border-r sm:px-3 sm:py-4"
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
                  onClick={() => onTabChange(tab.id)}
                  onKeyDown={(event) => onTabKeyDown(event, index)}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-xl px-3.5 py-2 text-left text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:whitespace-normal",
                    selected
                      ? "bg-surface-alt text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-surface-alt",
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

          <div ref={panelRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">
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

        {/* Footer */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-[var(--divider)] px-5 py-3.5 sm:px-7">
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
      </div>
    </div>
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

/** The heading that opens a group of fields within one tab panel. */
export function EditorSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-7 last:mb-0">
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
