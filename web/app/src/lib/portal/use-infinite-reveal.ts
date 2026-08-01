"use client";

import * as React from "react";

/**
 * Progressive reveal for the recommendation feeds (Papers, Grants, Fellowships,
 * Conferences).
 *
 * Every one of those feeds is fetched whole in a single request, so there is no
 * network page to wait on — what used to gate the tail was a "Show all" button.
 * This hook replaces that hard stop with an infinite scroll: the caller renders
 * `visible`, drops `sentinelRef` just below the list, and as the reader
 * approaches the end the next slice is revealed on its own.
 *
 * Notes on the behaviour that matter:
 * - The observer is torn down and re-created on every `count` change. Re-observing
 *   re-fires the callback against the current state, so if the sentinel is *still*
 *   in view after a reveal the next slice follows — the feed keeps up with a fast
 *   scroll instead of stalling one page behind.
 * - Reveals are delayed a beat so the shimmer below the list is actually seen;
 *   content that snaps in with no transition reads as a layout jump.
 * - `resetKey` re-collapses the feed to the first page. Callers pass their filter
 *   state so changing a filter starts the reader back at the top of the results.
 * - Without `IntersectionObserver` (older browsers, jsdom) everything is revealed
 *   at once, so the tail is never unreachable.
 */

/** How far below the viewport the sentinel starts pulling the next slice in. */
const ROOT_MARGIN = "480px 0px";

/** A beat between "sentinel seen" and "slice revealed", so the shimmer registers. */
const REVEAL_DELAY_MS = 220;

export type InfiniteReveal<T> = {
  /** The slice to render right now. */
  visible: T[];
  /** More items remain below the revealed slice. */
  hasMore: boolean;
  /** How many items are still hidden. */
  remaining: number;
  /** Attach to an element directly below the list. */
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  /** Reveal the next slice by hand (the keyboard fallback). */
  revealMore: () => void;
};

export function useInfiniteReveal<T>(
  items: T[],
  pageSize: number,
  /** Changing this collapses the feed back to its first page. */
  resetKey?: unknown,
): InfiniteReveal<T> {
  const total = items.length;
  const [state, setState] = React.useState({ count: pageSize, resetKey });
  const sentinelRef = React.useRef<HTMLDivElement | null>(null);

  // A new filter selection (or a new page size) means a new result set — send the
  // reader back to the first page rather than leaving them deep in a list whose
  // contents just changed underneath them. Adjusting during render rather than in
  // an effect keeps the collapsed list from flashing on screen first.
  let count = state.count;
  if (state.resetKey !== resetKey) {
    count = pageSize;
    setState({ count, resetKey });
  }

  const setCount = React.useCallback(
    (next: (prev: number) => number) => {
      setState((prev) => ({ ...prev, count: next(prev.count) }));
    },
    [],
  );

  // Without IntersectionObserver nothing would ever reveal the tail, so show it
  // all. Guarded on `window` so the server (which also lacks the constructor)
  // still renders the first page and hydration matches.
  const canObserve =
    typeof window === "undefined" || typeof IntersectionObserver !== "undefined";
  const shown = canObserve ? Math.min(count, total) : total;
  const hasMore = shown < total;

  const revealMore = React.useCallback(() => {
    setCount((prev) => Math.min(prev + pageSize, total));
  }, [setCount, pageSize, total]);

  React.useEffect(() => {
    if (!hasMore || typeof IntersectionObserver === "undefined") return;
    const el = sentinelRef.current;
    if (!el) return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    const observer = new IntersectionObserver(
      (entries) => {
        if (timer) return;
        if (!entries.some((entry) => entry.isIntersecting)) return;
        timer = setTimeout(() => {
          timer = null;
          setCount((prev) => Math.min(prev + pageSize, total));
        }, REVEAL_DELAY_MS);
      },
      { rootMargin: ROOT_MARGIN },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      if (timer) clearTimeout(timer);
    };
    // `shown` is a dependency on purpose: re-observing after a reveal is what
    // lets a fast scroll pull several slices in a row.
  }, [hasMore, pageSize, total, shown, setCount]);

  const visible = React.useMemo(() => items.slice(0, shown), [items, shown]);

  return { visible, hasMore, remaining: total - shown, sentinelRef, revealMore };
}

/**
 * The fade-up delay for a card at `index` within a feed revealed `pageSize` at a
 * time. Staggering off the absolute index would give the 60th card a three-second
 * delay; staggering within its own slice keeps every newly revealed batch feeling
 * the same as the first.
 */
export function revealDelay(index: number, pageSize: number, step = 50): string {
  return `${(index % pageSize) * step}ms`;
}
