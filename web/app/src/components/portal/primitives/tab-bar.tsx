"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export type TabItem = {
  key: string;
  label: string;
  icon?: React.ReactNode;
  /** A count or short marker rendered after the label. */
  badge?: React.ReactNode;
};

/**
 * The workspace's underlined tab row.
 *
 * One row, one tab stop: arrow keys move between tabs, Home / End jump to the
 * ends, and the row scrolls sideways on a narrow screen rather than wrapping
 * into a second line — a wrapped tab row reads as broken layout, which is
 * exactly how the project page's first version looked.
 *
 * `size` is the only visual variant: `lg` for a tab bar that owns a page, `sm`
 * for one inside a panel.
 */
export function TabBar({
  items,
  active,
  onChange,
  ariaLabel,
  panelId,
  idPrefix,
  size = "lg",
  className,
}: {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  ariaLabel: string;
  /** The id of the panel these tabs control (for `aria-controls`). */
  panelId: string;
  /** Namespace for each tab's element id, so a page may host two tab rows. */
  idPrefix: string;
  size?: "lg" | "sm";
  className?: string;
}) {
  const refs = React.useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (event: React.KeyboardEvent) => {
    const order = items.map((i) => i.key);
    const index = order.indexOf(active);
    let next: string | null = null;
    if (event.key === "ArrowRight") next = order[(index + 1) % order.length];
    if (event.key === "ArrowLeft")
      next = order[(index - 1 + order.length) % order.length];
    if (event.key === "Home") next = order[0];
    if (event.key === "End") next = order[order.length - 1];
    if (next) {
      event.preventDefault();
      onChange(next);
      refs.current[next]?.focus();
    }
  };

  return (
    <div className={cn("border-b border-[var(--divider)]", className)}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        onKeyDown={onKeyDown}
        className="-mb-px flex gap-1 overflow-x-auto pb-px [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {items.map((item) => {
          const on = item.key === active;
          return (
            <button
              key={item.key}
              ref={(node) => {
                refs.current[item.key] = node;
              }}
              type="button"
              role="tab"
              id={`${idPrefix}-${item.key}`}
              aria-selected={on}
              aria-controls={panelId}
              tabIndex={on ? 0 : -1}
              onClick={() => onChange(item.key)}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                size === "lg"
                  ? "px-4 py-3 text-[13.5px]"
                  : "px-3 py-2.5 text-[12.5px]",
                on
                  ? "border-b-primary bg-[color-mix(in_srgb,var(--primary)_7%,transparent)] text-[var(--brand-primary-hover)]"
                  : "border-b-transparent text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-primary)]",
              )}
            >
              {item.icon}
              {item.label}
              {item.badge != null ? (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-[1px] text-[11px] font-semibold",
                    on
                      ? "bg-[color-mix(in_srgb,var(--primary)_15%,transparent)] text-primary"
                      : "bg-surface-alt text-[var(--text-secondary)]",
                  )}
                >
                  {item.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
