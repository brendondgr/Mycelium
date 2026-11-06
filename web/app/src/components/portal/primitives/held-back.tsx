"use client";

import * as React from "react";

import { ChevronDownIcon } from "@/components/portal/icons";
import type { Usability } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** The first check that holds an item back, or undefined. */
export function heldReason(usability: Usability | null | undefined): string | undefined {
  return usability?.checks.find((c) => c.status === "block")?.label;
}

/**
 * "Mylo held back" — the tail of a lab feed (beside "your filters hid"): items
 * that fit the lab's themes but failed a hard check, each with the reason. They
 * are never announced, and they stay one click away rather than gone.
 */
export function HeldBack({
  count,
  noun,
  children,
  className,
}: {
  count: number;
  noun: string;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  if (count < 1) return null;
  return (
    <div className={cn("mt-4", className)}>
      <div className="flex items-center gap-3">
        <span aria-hidden className="h-px flex-1 bg-border" />
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="inline-flex min-h-[32px] items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {open ? "Hide" : "Show"} the {count}{" "}
          {count === 1 ? noun.replace(/s$/, "") : noun} Mylo held back
          <ChevronDownIcon
            size={11}
            aria-hidden="true"
            className={cn(
              "transition-transform duration-150 motion-reduce:transition-none",
              open && "rotate-180",
            )}
          />
        </button>
        <span aria-hidden className="h-px flex-1 bg-border" />
      </div>
      {open ? (
        <div className="mt-3.5 space-y-3.5">
          <p className="m-0 text-center text-[12.5px] text-[var(--text-secondary)]">
            These fit the lab&apos;s themes but failed a hard check, so Mylo never
            announced them. Each card says which.
          </p>
          <div className="space-y-3.5 opacity-70 transition-opacity hover:opacity-100 motion-reduce:transition-none">
            {children}
          </div>
        </div>
      ) : null}
    </div>
  );
}
