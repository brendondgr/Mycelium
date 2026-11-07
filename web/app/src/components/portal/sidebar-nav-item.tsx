"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

type SidebarNavItemProps = {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
  /** Trailing element: a count pill, a "Soon" badge, etc. */
  trailing?: React.ReactNode;
  /** Icon-only, for the collapsed rail; the label stays as the accessible name. */
  collapsed?: boolean;
};

/**
 * One rail row: icon and label over a soft tint when it is the current page.
 * The state never rests on colour alone — the label goes heavier and the row
 * carries `aria-current="page"`. Collapsed, the row is the icon alone with the
 * label as its name and tooltip.
 */
export function SidebarNavItem({
  icon,
  label,
  active,
  onClick,
  trailing,
  collapsed = false,
}: SidebarNavItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
      className={cn(
        "relative flex w-full items-center gap-3 rounded-[10px] py-2.5 text-left text-[13.5px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        collapsed ? "justify-center px-0" : "pl-3.5 pr-3",
        active
          ? "bg-[color-mix(in_srgb,var(--primary)_14%,transparent)] font-semibold text-[var(--text-primary)]"
          : "font-medium text-[var(--text-secondary)]",
      )}
    >
      <span className="shrink-0">{icon}</span>
      {collapsed ? null : <span className="flex-1">{label}</span>}
      {trailing && !collapsed ? <span>{trailing}</span> : null}
    </button>
  );
}
