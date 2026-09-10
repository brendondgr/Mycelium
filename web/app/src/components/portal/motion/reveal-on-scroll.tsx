"use client";

import * as React from "react";

import { usePrefersReducedMotion } from "@/components/portal/motion/use-reduced-motion";
import { scrollParent } from "@/lib/portal/scroll-parent";
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
 * This plays the entrance off the scroll position instead. Two earlier settings
 * were both wrong in opposite directions. Running far ahead of the scroll meant
 * the animation finished off screen and the feed seemed to snap into place fully
 * formed — the same complaint the mount-triggered version had. Holding a card
 * back until it was genuinely *inside* the panel meant the reader scrolled to a
 * card and then waited on it, which reads as the feed being slow to load rather
 * than as an entrance at all.
 *
 * The lead below is therefore small and positive: a card starts its fade as its
 * top edge comes up on the fold, so it is arriving as the reader reaches it and
 * settled a moment later. Paired with the short stagger cap in `revealDelay`,
 * nothing on screen is ever waiting on an animation it cannot see.
 *
 * Fires once per card. A twenty-five card feed replaying every time the reader
 * scrolls back up would be nausea, not polish.
 */

/**
 * How far *past* the scroll port's bottom edge a card starts, as a share of the
 * port's height — a tenth of a screen of lead, not a screenful.
 */
const LEAD = 0.1;

type Ctl = {
  observe: (el: Element, onSeen: () => void) => () => void;
};

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
