"use client";

import * as React from "react";

import { scrollParent } from "@/lib/portal/scroll-parent";

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
 * - The observer is rooted on the feed's own scroll container. It used to run on
 *   the default viewport root, which made its lead margin inert: `main` clips
 *   before the viewport does, so the sentinel could not be seen until it reached
 *   the panel edge, and the next slice only started arriving once the reader was
 *   already at the bottom of the list.
 * - Reveals are immediate. There is no request behind them — the whole feed is
 *   already in memory — so a delay here buys nothing but a wait, and the shimmer
 *   it was there to show is the thing the reader is trying to scroll past.
 * - A passive scroll listener measures the same lead as a backstop, so a browser
 *   whose observer never delivers still walks the feed instead of stopping dead
 *   at the first slice.
 * - `resetKey` re-collapses the feed to the first page. Callers pass their filter
 *   state so changing a filter starts the reader back at the top of the results.
 * - Without `IntersectionObserver` (older browsers, jsdom) everything is revealed
 *   at once, so the tail is never unreachable.
 */

/**
 * How far below the scroll port the sentinel starts pulling the next slice in.
 * A screenful and a half: far enough that the next batch is rendered well before
 * the reader arrives, close enough that a feed of a hundred-odd items is not
 * effectively mounted whole on first paint.
 */
const LEAD_PX = 1400;
const ROOT_MARGIN = `${LEAD_PX}px 0px`;

/** Minimum gap between two backstop measurements, however fast the scroll. */
const THROTTLE_MS = 100;

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

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setCount((prev) => Math.min(prev + pageSize, total));
      },
      // Rooted on the scroller, or the viewport when the page itself scrolls —
      // `ROOT_MARGIN` only means anything against the box that actually clips.
      { root: scrollParent(el), rootMargin: ROOT_MARGIN },
    );
    observer.observe(el);
    return () => observer.disconnect();
    // `shown` is a dependency on purpose: re-observing after a reveal is what
    // lets a fast scroll pull several slices in a row.
  }, [hasMore, pageSize, total, shown, setCount]);

  /*
   * The backstop, and on some browsers the only thing that actually runs.
   *
   * An IntersectionObserver that never delivers leaves this feed frozen at its
   * first slice with no way down but the screen-reader-only "Load more" button —
   * which is indistinguishable, from the reader's side, from a feed that takes
   * forever to load anything. `RevealOnScroll` already owes and pays this
   * guarantee for a card it has hidden; the hook that owns the whole tail of the
   * list owes it more.
   *
   * So: measure the sentinel against the scroll port on the reader's own scroll,
   * rAF-throttled and passive, and reveal on the same lead the observer uses. It
   * runs once on attach too, so a slice that lands with the sentinel already in
   * range fills in without needing a scroll to start it.
   */
  React.useEffect(() => {
    if (!hasMore) return;
    const el = sentinelRef.current;
    if (!el) return;
    const scroller = scrollParent(el);
    const target: Element | Window = scroller ?? window;

    // Throttled on a timestamp rather than a frame. `requestAnimationFrame` is
    // the usual choice and the wrong one here: a callback scheduled on a frame
    // that never comes is a backstop that fails in exactly the conditions it
    // exists for. Two rect reads, at most ten times a second, is a cost worth
    // paying for a measurement that always happens.
    let last = 0;
    const measure = () => {
      const now = Date.now();
      if (now - last < THROTTLE_MS) return;
      last = now;
      const node = sentinelRef.current;
      if (!node) return;
      const portBottom = scroller
        ? scroller.getBoundingClientRect().bottom
        : window.innerHeight;
      if (node.getBoundingClientRect().top - portBottom <= LEAD_PX) {
        setCount((prev) => Math.min(prev + pageSize, total));
      }
    };

    target.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure, { passive: true });
    measure();
    return () => {
      target.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
    // `shown` again: re-measuring after a reveal is what lets one long scroll
    // pull several slices rather than one per scroll event.
  }, [hasMore, pageSize, total, shown, setCount]);

  const visible = React.useMemo(() => items.slice(0, shown), [items, shown]);

  return { visible, hasMore, remaining: total - shown, sentinelRef, revealMore };
}

/**
 * How many stagger steps a card's entrance may be held for, however deep into
 * its slice it sits.
 *
 * Without a cap, a twenty-five card slice at 50ms a step delayed its last card by
 * 1.2 seconds. That is fine for a batch that appears together — the eye reads it
 * as one wave — but `RevealOnScroll` fires each card as it comes into view, one
 * at a time, so the delay landed on a single card the reader was looking straight
 * at. Scrolling down meant arriving at a blank card and waiting a second for it,
 * which is exactly the "nothing is loading" complaint the stagger was supposed to
 * prevent.
 */
const MAX_STAGGER_STEPS = 3;

/**
 * The fade-up delay for a card at `index` within a feed revealed `pageSize` at a
 * time. Staggering off the absolute index would give the 60th card a three-second
 * delay; staggering within its own slice keeps every newly revealed batch feeling
 * the same as the first, and the cap keeps any one card's wait under a fifth of a
 * second.
 */
export function revealDelay(index: number, pageSize: number, step = 50): string {
  return `${Math.min(index % pageSize, MAX_STAGGER_STEPS) * step}ms`;
}
