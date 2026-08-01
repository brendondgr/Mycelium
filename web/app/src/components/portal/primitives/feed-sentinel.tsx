"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";

/**
 * The foot of an infinitely scrolling recommendation feed.
 *
 * While items remain it renders the scroll sentinel plus a shimmer placeholder,
 * so the reader sees the feed reaching for more rather than a page that simply
 * stops. Once everything is shown it settles into a quiet end-of-feed rule.
 *
 * Two accessibility obligations ride along with the auto-load:
 * - a keyboard user who never scrolls with a pointer still gets a real control —
 *   the "Load more" button is `sr-only` until focused, then becomes visible.
 * - the count is announced politely, so a screen-reader user is told the feed
 *   grew instead of silently gaining rows.
 */
export function FeedSentinel({
  sentinelRef,
  hasMore,
  remaining,
  onRevealMore,
  totalShown,
  /** Plural noun for this feed: "papers", "grants", "fellowships", … */
  noun,
}: {
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  hasMore: boolean;
  remaining: number;
  onRevealMore: () => void;
  totalShown: number;
  noun: string;
}) {
  if (!hasMore) {
    return totalShown > 0 ? (
      <p className="mt-6 flex items-center justify-center gap-3 text-xs text-[var(--text-secondary)]">
        <span aria-hidden className="h-px w-8 bg-border" />
        That&rsquo;s all {totalShown} {noun} for now
        <span aria-hidden className="h-px w-8 bg-border" />
      </p>
    ) : null;
  }

  return (
    <div className="mt-3.5">
      <div ref={sentinelRef} aria-hidden className="h-px w-full" />

      <div className="space-y-3.5" aria-hidden>
        <ShimmerCard />
        <ShimmerCard />
      </div>

      <p aria-live="polite" className="sr-only">
        {remaining} more {noun} below.
      </p>

      <div className="mt-3.5 flex justify-center">
        <button
          type="button"
          onClick={onRevealMore}
          className="sr-only rounded-full border border-border bg-surface-alt px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-surface focus:not-sr-only focus:outline-none focus:ring-2 focus:ring-ring"
        >
          Load {remaining} more {noun}
        </button>
      </div>
    </div>
  );
}

/** A card-shaped shimmer standing in for the slice about to be revealed. */
function ShimmerCard() {
  return (
    <Card className="overflow-hidden p-5 opacity-70">
      <div className="flex items-start gap-4">
        <span className="h-11 w-11 flex-none rounded-full bg-surface-alt motion-safe:animate-pulse" />
        <div className="min-w-0 flex-1 space-y-2.5">
          <span className="block h-4 w-2/3 rounded bg-surface-alt motion-safe:animate-pulse" />
          <span className="block h-3 w-1/3 rounded bg-surface-alt motion-safe:animate-pulse" />
          <span className="block h-3 w-full rounded bg-surface-alt motion-safe:animate-pulse" />
        </div>
      </div>
    </Card>
  );
}
