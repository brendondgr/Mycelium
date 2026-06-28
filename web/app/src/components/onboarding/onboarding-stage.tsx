"use client";

import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export type OnboardingStageProps = {
  /** Index of the active step. */
  current: number;
  /** Kept for API compatibility; slide direction derives from the index offset. */
  direction?: number;
  /** The rendered step panels, one per step. */
  steps: React.ReactNode[];
  className?: string;
};

// The active card spans CARD_WIDTH of the stage and is centered; because the
// adjacent panels are translated by exactly the card width, the previous and
// next cards sit flush beside it (no overlap, nothing hidden behind), showing a
// translucent slice on each side. A soft edge mask fades those slices out so
// there is no hard cut-off line.
const PEEK_OPACITY = 0.5;
const PEEK_SCALE = 0.92;
const SLIDE_EASE = "cubic-bezier(0.32, 0.01, 0.12, 1)";
const SLIDE_MS = 550;
const EDGE_FADE = "linear-gradient(to right, transparent 0%, #000 6%, #000 94%, transparent 100%)";

/** True on viewports wide enough to comfortably show side cards. */
function useIsWide(): boolean {
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 640px)");
    const update = () => setWide(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return wide;
}

export default function OnboardingStage({
  current,
  steps,
  className,
}: OnboardingStageProps) {
  const reduce = useReducedMotion();
  const wide = useIsWide();
  const panelRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [height, setHeight] = useState<number | undefined>(undefined);

  // On wide screens the active card is narrower so a clear slice of the
  // previous/next cards shows; on phones it is near-full-width with a hint.
  const cardWidth = wide ? 70 : 90;

  // Drive the stage height from the active panel so short steps don't leave a
  // tall gap and the container resizes smoothly between steps.
  useLayoutEffect(() => {
    const el = panelRefs.current[current];
    if (!el) {
      return;
    }
    const measure = () => setHeight(el.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [current, steps, cardWidth]);

  const panelTransition = reduce
    ? undefined
    : `transform ${SLIDE_MS}ms ${SLIDE_EASE}, opacity ${SLIDE_MS}ms ease`;

  return (
    <div
      className={cn("relative w-full overflow-hidden", className)}
      style={{
        height,
        transition: reduce ? undefined : `height ${SLIDE_MS}ms ease`,
        WebkitMaskImage: EDGE_FADE,
        maskImage: EDGE_FADE,
      }}
    >
      {steps.map((panel, index) => {
        const offset = index - current;
        const isActive = offset === 0;
        const isNeighbour = Math.abs(offset) === 1;
        return (
          <div
            key={index}
            ref={(el) => {
              panelRefs.current[index] = el;
            }}
            className="absolute inset-x-0 top-0 w-full"
            aria-hidden={!isActive}
            inert={isActive ? undefined : true}
            style={{
              pointerEvents: isActive ? "auto" : "none",
              transform: `translateX(${offset * cardWidth}%)`,
              transition: panelTransition,
            }}
          >
            <div
              className="mx-auto"
              style={{
                width: `${cardWidth}%`,
                opacity: isActive ? 1 : isNeighbour ? PEEK_OPACITY : 0,
                transform: `scale(${isActive ? 1 : PEEK_SCALE})`,
                transformOrigin: offset < 0 ? "right center" : "left center",
                transition: panelTransition,
              }}
            >
              {panel}
            </div>
          </div>
        );
      })}
    </div>
  );
}
