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
 * This plays the entrance off the scroll position instead, and plays it *where
 * the reader is looking*. An earlier version ran ahead of the scroll, starting
 * each card's fade while it was still below the fold on the theory that content
 * should be settled by the time you reach it. That turns out to be the wrong
 * trade: the animation happens off screen and the feed just seems to snap into
 * place fully formed — the same complaint the mount-triggered version had. The
 * margin below is therefore negative, holding a card back until it is genuinely
 * inside the panel rather than clipping its bottom edge.
 *
 * Fires once per card. A twenty-five card feed replaying every time the reader
 * scrolls back up would be nausea, not polish.
 */

/**
 * How far *inside* the scroll port a card must come before it starts, as a
 * share of the port's height. Negative on purpose — see above.
 */
const LEAD = -0.08;

type Ctl = {
  observe: (el: Element, onSeen: () => void) => () => void;
};

/**
 * The workspace scrolls inside `<main>`, not the window, so the observer has to
 * be rooted on that element. `rootMargin` adjusts the *root*'s box, but
 * clipping by intermediate ancestors is applied without it — left on the
 * default viewport root, the margin would be measured against the viewport
 * while `main`'s own box did the real clipping, and cards would trip the
 * observer at the wrong moment.
 *
 * Falling back to the viewport keeps this working anywhere the page itself is
 * the scroller.
 */
function scrollParent(el: Element): Element | null {
  let node: Element | null = el.parentElement;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    // Identified by its overflow alone, deliberately: whether it happens to be
    // overflowing *right now* is not the question. A feed mounts its skeletons
    // first, so `main` is not yet taller than its box, and a check for that
    // would send the first batch of cards to a viewport-rooted observer that
    // can never see past `main`'s clip — leaving them invisible.
    if (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") {
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

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const fire = seen.get(entry.target);
        observer.unobserve(entry.target);
        pending.delete(entry.target);
        fire?.();
      }
    },
    // A percentage in rootMargin resolves against the root's own box.
    {
      root,
      rootMargin: `0px 0px ${Math.round(LEAD * 100)}% 0px`,
      threshold: 0,
    },
  );

  /*
   * Failsafe, mirroring the public site's. This component is the only thing
   * that ever hides a card, so it owes a guarantee that it can show it again:
   * if nothing at all has revealed a short while after the first card is
   * observed, the observer is not working in this environment and everything
   * pending is shown rather than left invisible. One check per container, not
   * one timer per card.
   */
  let everFired = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const armFailsafe = () => {
    // Re-armed on every batch until something has actually fired. Arming only
    // once would cover the first slice and then leave every later slice — the
    // ones the infinite scroll adds — with no protection at all.
    if (everFired || timer) return;
    timer = setTimeout(() => {
      timer = null;
      if (everFired) return;
      for (const el of [...pending]) {
        const fire = seen.get(el);
        observer.unobserve(el);
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
      observer.observe(el);
      armFailsafe();
      return () => {
        observer.unobserve(el);
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
