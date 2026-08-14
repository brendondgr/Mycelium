"use client";

import * as React from "react";

/**
 * The foot of an infinitely scrolling recommendation feed.
 *
 * While items remain it renders the scroll sentinel plus a thread growing down
 * out of the feed and branching — the network reaching for the next page rather
 * than a page that simply stops. Once everything is shown it settles into a
 * quiet end-of-feed rule.
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

      <div className="flex flex-col items-center gap-2 pt-2">
        <GrowingThread />
        <p className="text-xs text-[var(--text-secondary)]">
          Finding more {noun}&hellip;
        </p>
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

/**
 * A hypha growing down out of the feed: a trunk that draws itself, two branches
 * that follow, and three nodes that bloom where they land — the last one gold,
 * the colour this product reserves for a find worth having.
 *
 * The whole thing is drawn statically in the markup (`strokeDashoffset: 0`,
 * nodes at full scale). The animation classes only exist inside the
 * `prefers-reduced-motion: no-preference` block in `globals.css`, so a reader
 * who asked for stillness gets a finished, legible thread instead of an empty
 * frame — and no client-side branch is needed to decide which.
 */
function GrowingThread() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 120 140"
      width={104}
      height={122}
      fill="none"
      className="overflow-visible"
    >
      {[
        { d: "M60 0 C60 26 56 40 58 62 C60 84 56 98 59 132", w: 1.5, o: 1, delay: "0ms" },
        { d: "M58 60 C46 68 40 78 33 94", w: 1.1, o: 0.7, delay: "240ms" },
        { d: "M58 74 C70 82 78 90 88 104", w: 1.1, o: 0.7, delay: "420ms" },
      ].map((seg) => (
        <path
          key={seg.d}
          d={seg.d}
          pathLength={100}
          stroke="var(--primary)"
          strokeWidth={seg.w}
          strokeLinecap="round"
          opacity={seg.o}
          className="mycelium-thread"
          style={{ strokeDasharray: 100, strokeDashoffset: 0, animationDelay: seg.delay }}
        />
      ))}
      {[
        { cx: 33, cy: 94, r: 2.6, fill: "var(--primary)", delay: "520ms" },
        { cx: 88, cy: 104, r: 2.6, fill: "var(--primary)", delay: "700ms" },
        { cx: 59, cy: 132, r: 3.2, fill: "var(--accent)", delay: "900ms" },
      ].map((node) => (
        <g
          key={`${node.cx}-${node.cy}`}
          className="mycelium-node"
          style={{
            transformBox: "fill-box",
            transformOrigin: "center",
            animationDelay: node.delay,
          }}
        >
          <circle cx={node.cx} cy={node.cy} r={node.r} fill={node.fill} />
        </g>
      ))}
    </svg>
  );
}
