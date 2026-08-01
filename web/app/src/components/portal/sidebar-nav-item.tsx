"use client";

import * as React from "react";

import { LeafVine } from "@/components/portal/leaf-vine";
import { cn } from "@/lib/utils";

type SidebarNavItemProps = {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
  /** Trailing element: a count pill, a "Soon" badge, etc. */
  trailing?: React.ReactNode;
};

/**
 * One sidebar row. Selecting a row leaves its hover animation in its finished
 * state — the vine stays drawn and gently sways — over a soft tint. There is
 * deliberately no left accent rule: the grown vine is the selection mark. The
 * state never rests on color alone, since the label also goes heavier/darker and
 * the row carries `aria-current="page"`, so it still reads under the contrast
 * and reduced-motion expectations in the style guide.
 */
export function SidebarNavItem({
  icon,
  label,
  active,
  onClick,
  trailing,
}: SidebarNavItemProps) {
  const [engaged, setEngaged] = React.useState(false);
  // The vine grows on hover, keyboard focus, or when the row is the active page.
  const grown = active || engaged;

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setEngaged(true)}
      onMouseLeave={() => setEngaged(false)}
      onFocus={() => setEngaged(true)}
      onBlur={() => setEngaged(false)}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex w-full items-center gap-3 rounded-[10px] py-2.5 pl-4 pr-3 text-left text-[13.5px] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "font-semibold text-[var(--text-primary)]"
          : "font-medium text-[var(--text-secondary)]",
      )}
    >
      <LeafVine grown={grown} active={active} />
      {active ? (
        <span
          aria-hidden
          className="absolute inset-0 rounded-[10px] bg-[color-mix(in_srgb,var(--primary)_13%,transparent)]"
        />
      ) : null}
      <span className="relative z-[2] shrink-0">{icon}</span>
      <span className="relative z-[2] flex-1">{label}</span>
      {trailing ? <span className="relative z-[2]">{trailing}</span> : null}
    </button>
  );
}
