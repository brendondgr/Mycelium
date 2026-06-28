"use client";

import React, { useLayoutEffect, useRef, useState } from "react";
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

// Each step card spans CARD_WIDTH of the stage and is centered; neighbours sit
// SLIDE_STEP apart (a percentage of the card's own width) so the next step peeks
// in from the right and the previous from the left while the active step stays
// centered. Plain CSS transforms/transitions keep this reliable and able to
// settle (no animation-library lifecycle to stall).
const CARD_WIDTH = "88%";
const SLIDE_STEP = 90; // percent of the card width between adjacent steps
const PEEK_OPACITY = 0.4;
const PEEK_SCALE = 0.94;
const SLIDE_EASE = "cubic-bezier(0.32, 0.01, 0.12, 1)";
const SLIDE_MS = 550;

export default function OnboardingStage({
  current,
  steps,
  className,
}: OnboardingStageProps) {
  const reduce = useReducedMotion();
  const panelRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [height, setHeight] = useState<number | undefined>(undefined);

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
  }, [current, steps]);

  const panelTransition = reduce
    ? undefined
    : `transform ${SLIDE_MS}ms ${SLIDE_EASE}, opacity ${SLIDE_MS}ms ease`;

  return (
    <div
      className={cn("relative w-full overflow-hidden", className)}
      style={{
        height,
        transition: reduce ? undefined : `height ${SLIDE_MS}ms ease`,
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
            className="absolute inset-x-0 top-0 mx-auto"
            aria-hidden={!isActive}
            inert={isActive ? undefined : true}
            style={{
              width: CARD_WIDTH,
              zIndex: isActive ? 10 : 0,
              pointerEvents: isActive ? "auto" : "none",
              opacity: isActive ? 1 : isNeighbour ? PEEK_OPACITY : 0,
              transform: `translateX(${offset * SLIDE_STEP}%) scale(${
                isActive ? 1 : PEEK_SCALE
              })`,
              transition: panelTransition,
            }}
          >
            {panel}
          </div>
        );
      })}
    </div>
  );
}
