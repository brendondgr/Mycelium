"use client";

import * as React from "react";

import { ChevronDownIcon } from "@/components/portal/icons";
import { cn } from "@/lib/utils";

/**
 * The tail of a filtered feed: what the rail's facets took out, and the way to
 * look at it anyway.
 *
 * A filter that silently deletes rows leaves the reader unable to tell a narrow
 * result from an empty corpus — "three conferences" reads the same whether the
 * run found three or found sixty and hid fifty-seven. So the count is always
 * stated, and the rows themselves are one click away rather than gone.
 *
 * Collapsed by default: the reader asked for these to be out of the way, and
 * opening with them on screen would undo the filter they just set. The revealed
 * rows are dimmed until hovered so a glance can still tell them apart from the
 * feed proper, and the whole block renders nothing when the filters hid nothing.
 */
export function HiddenByFilters({
  count,
  noun,
  children,
  className,
}: {
  /** How many rows the rail's facets removed from the scoped feed. */
  count: number;
  /** Plural noun for the copy — "conferences", "grants", "fellowships". */
  noun: string;
  /** The hidden rows, rendered only once the reader opens the block. */
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
          className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {open ? "Hide" : "Show"} the {count}{" "}
          {count === 1 ? singular(noun) : noun} your filters hid
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
        <div className="mt-3.5 space-y-3.5 opacity-60 transition-opacity hover:opacity-100 motion-reduce:transition-none">
          {children}
        </div>
      ) : null}
    </div>
  );
}

/** "conferences" -> "conference". The three feeds only ever pass regular plurals. */
function singular(noun: string): string {
  return noun.endsWith("s") ? noun.slice(0, -1) : noun;
}
