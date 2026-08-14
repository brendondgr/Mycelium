"use client";

import * as React from "react";

/**
 * The user's `prefers-reduced-motion` setting, live.
 *
 * SSR-safe: it reports `false` on the server and on the first client render,
 * then corrects itself in an effect. That ordering matters — the alternative
 * (assume reduced, then animate) makes every page flash its decorations in for
 * the people who asked not to see them.
 *
 * A decorative layer that reads `true` here should render *nothing*, not a
 * slowed-down version of itself. The static state it leaves behind has to carry
 * the meaning on its own.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = React.useState(false);

  React.useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}
