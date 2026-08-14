"use client";

import * as React from "react";

/**
 * Fires once, the first time the element is meaningfully on screen, and never
 * rearms.
 *
 * This is the guard that makes an entrance animation tolerable in a feed: the
 * observer disconnects on the first hit, so scrolling back up a list of
 * twenty-five cards does not replay twenty-five animations. It is also why the
 * hook returns a boolean that only ever goes false → true.
 *
 * Environments without IntersectionObserver (and readers who prefer reduced
 * motion, via `enabled: false`) resolve to `true` immediately, which callers
 * should treat as "show the finished state now".
 */
export function useInViewOnce<T extends Element>(
  { enabled = true, threshold = 0.55 }: { enabled?: boolean; threshold?: number } = {},
): [React.RefObject<T | null>, boolean] {
  const ref = React.useRef<T | null>(null);
  const [seen, setSeen] = React.useState(false);

  React.useEffect(() => {
    if (!enabled || seen) return;
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      // Deferred rather than set inline: the initial render has to match the
      // server's (which cannot know about the observer either), so this settles
      // on the next tick instead of cascading a render inside the effect.
      const settle = setTimeout(() => setSeen(true), 0);
      return () => clearTimeout(settle);
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [enabled, seen, threshold]);

  return [ref, seen];
}
