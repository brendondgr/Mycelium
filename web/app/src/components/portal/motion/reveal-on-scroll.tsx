"use client";

import * as React from "react";

import { usePrefersReducedMotion } from "@/components/portal/motion/use-reduced-motion";
import { cn } from "@/lib/utils";

/**
 * A feed card's entrance, played when the reader is *about* to reach it.
 *
 * The workspace already had entrance animations, but they were plain CSS
 * animations on mount: a slice of ten cards revealed by the infinite scroll all
 * ran their fade at once, whether or not any of them was on screen. Anything
 * below the fold had therefore finished animating long before the reader
 * scrolled down to it, so past the first screenful the feed simply appeared,
 * fully formed, exactly the static effect the animation was there to avoid.
 *
 * This plays the entrance off the scroll position instead, and starts it
 * *early*. The observer's root runs past the bottom of the viewport, so a card
 * begins its fade while it is still below the fold and is settled by the time
 * it is actually visible — the feed reads as arriving just ahead of the reader
 * rather than catching up behind them.
 *
 * How far ahead scales with scroll speed: a slow reader gets a short lead so the
 * entrance still plays somewhere they can see it, and a fast scroll gets a long
 * one, because otherwise a flick down the page is a wall of half-faded cards.
 *
 * Fires once per card. A twenty-five card feed replaying every time the reader
 * scrolls back up would be nausea, not polish.
 */

/** Lead distance below the fold, as a share of viewport height. */
const LEAD_SLOW = 0.3;
const LEAD_FAST = 1;
/** Above this scroll speed (px/s) the long lead applies. */
const FAST_PX_PER_S = 900;

type Ctl = {
  observe: (el: Element, onSeen: () => void) => () => void;
};

/**
 * The workspace scrolls inside `<main>`, not the window, and that changes two
 * things that are easy to get wrong:
 *
 *   - `rootMargin` expands the *root*, but clipping by intermediate ancestors
 *     is applied without it. Left on the default viewport root, the lead would
 *     be clipped away by `main`'s own box and nothing would ever reveal early.
 *     So the scroll container becomes the root.
 *   - `scroll` events do not bubble, so a listener on `window` never hears the
 *     container move and the fast lead would never engage.
 *
 * Hence: find the nearest scrollable ancestor, root the observer on it, and
 * listen to it. Falling back to the viewport keeps this working anywhere the
 * page itself is the scroller.
 */
function scrollParent(el: Element): Element | null {
  let node: Element | null = el.parentElement;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    if (
      (overflowY === "auto" || overflowY === "scroll") &&
      node.scrollHeight > node.clientHeight
    ) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

/**
 * One observer per scroll container, shared by every card inside it, rather
 * than one observer each. A feed can hold a hundred cards, and a hundred
 * IntersectionObservers plus a hundred scroll listeners is real main-thread
 * cost for an effect nobody asked to pay for.
 */
function createController(root: Element | null): Ctl {
  const seen = new WeakMap<Element, () => void>();
  const pending = new Set<Element>();
  let observer: IntersectionObserver | null = null;
  let speed: "slow" | "fast" = "slow";

  const build = (next: "slow" | "fast") => {
    speed = next;
    observer?.disconnect();
    const lead = next === "fast" ? LEAD_FAST : LEAD_SLOW;
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const fire = seen.get(entry.target);
          observer?.unobserve(entry.target);
          pending.delete(entry.target);
          fire?.();
        }
      },
      // A percentage in rootMargin resolves against the root's own box, so this
      // reads as "a third of a screenful further down".
      {
        root,
        rootMargin: `0px 0px ${Math.round(lead * 100)}% 0px`,
        threshold: 0,
      },
    );
    for (const el of pending) observer.observe(el);
  };

  build("slow");

  const readY = () => (root ? root.scrollTop : window.scrollY);
  let lastY = readY();
  let lastT = performance.now();
  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      if (pending.size === 0) return;
      const now = performance.now();
      const dt = now - lastT;
      if (dt < 60) return;
      const y = readY();
      const v = (Math.abs(y - lastY) / dt) * 1000;
      lastY = y;
      lastT = now;
      const want = v > FAST_PX_PER_S ? "fast" : "slow";
      if (want !== speed) build(want);
    });
  };
  (root ?? window).addEventListener("scroll", onScroll, { passive: true });

  /*
   * Failsafe, mirroring the public site's. This component is the only thing
   * that ever hides a card, so it owes a guarantee that it can show it again:
   * if nothing at all has revealed a short while after the first card is
   * observed, the observer is not working in this environment and everything
   * pending is shown rather than left invisible. One check per container, not
   * one timer per card.
   */
  let everFired = false;
  let armed = false;
  const armFailsafe = () => {
    if (armed) return;
    armed = true;
    setTimeout(() => {
      if (everFired) return;
      for (const el of [...pending]) {
        const fire = seen.get(el);
        observer?.unobserve(el);
        pending.delete(el);
        fire?.();
      }
    }, 2000);
  };

  return {
    observe(el, onSeen) {
      seen.set(el, () => {
        everFired = true;
        onSeen();
      });
      pending.add(el);
      observer?.observe(el);
      armFailsafe();
      return () => {
        observer?.unobserve(el);
        pending.delete(el);
        seen.delete(el);
      };
    },
  };
}

/** One controller per scroll container, created on first use. */
const controllers = new WeakMap<Element, Ctl>();
let windowController: Ctl | null = null;

function getController(el: Element): Ctl | null {
  if (typeof window === "undefined" || typeof IntersectionObserver === "undefined") {
    return null;
  }
  const root = scrollParent(el);
  if (!root) {
    windowController ??= createController(null);
    return windowController;
  }
  let ctl = controllers.get(root);
  if (!ctl) {
    ctl = createController(root);
    controllers.set(root, ctl);
  }
  return ctl;
}

export function RevealOnScroll({
  children,
  /** Stagger within the revealed slice, e.g. `revealDelay(index, pageSize)`. */
  delay,
  className,
}: {
  children: React.ReactNode;
  delay?: string;
  className?: string;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [shown, setShown] = React.useState(false);

  React.useEffect(() => {
    if (shown) return;
    // Reduced motion, or no observer to work with: show it now. Deferred by a
    // tick rather than set inline — the first client render has to match the
    // server's, which cannot know about either, so this settles afterwards
    // instead of cascading a render from inside the effect. Same reasoning (and
    // same shape) as `useInViewOnce`.
    const el = ref.current;
    const ctl = reducedMotion || !el ? null : getController(el);
    if (!ctl || !el) {
      const settle = setTimeout(() => setShown(true), 0);
      return () => clearTimeout(settle);
    }
    return ctl.observe(el, () => setShown(true));
  }, [reducedMotion, shown]);

  return (
    <div
      ref={ref}
      className={cn(shown ? "portal-fade-up" : "portal-reveal-pending", className)}
      style={shown && delay ? { animationDelay: delay } : undefined}
    >
      {children}
    </div>
  );
}
