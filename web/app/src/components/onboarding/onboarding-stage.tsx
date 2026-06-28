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

// A coverflow "deck": the active card is crisp and centred; the previous and
// next cards stay (mostly) fully visible as translucent, scaled-down cards that
// drop slightly and sit to the sides — bleeding into the page margins rather
// than being clipped to a sliver. Tune these to taste.
const SIDE_SCALE = 0.86; // how much smaller the side cards are
const SIDE_DROP = 18; // px the side cards drop ("moves down into the left")
const SIDE_OPACITY = 0.5; // translucency of the side cards
const SLIDE_EASE = "cubic-bezier(0.32, 0.01, 0.12, 1)";
const SLIDE_MS = 560;

export default function OnboardingStage({
  current,
  steps,
  className,
}: OnboardingStageProps) {
  const reduce = useReducedMotion();
  const panelRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [height, setHeight] = useState<number | undefined>(undefined);

  // Drive the stage height from the active card so short steps don't leave a
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

  const transition = reduce
    ? undefined
    : `transform ${SLIDE_MS}ms ${SLIDE_EASE}, opacity ${SLIDE_MS}ms ease`;

  return (
    // overflow-visible lets the side cards extend into the page margins (the
    // onboarding page clips the viewport with overflow-x-hidden). `--peek` is the
    // sideways travel per step, smaller on wide screens where there is more room.
    <div
      className={cn("relative w-full [--peek:78%] sm:[--peek:60%]", className)}
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
            className="absolute inset-x-0 top-0 w-full"
            aria-hidden={!isActive}
            inert={isActive ? undefined : true}
            style={
              {
                "--off": String(offset),
                zIndex: isActive ? 30 : isNeighbour ? 20 : 10,
                pointerEvents: isActive ? "auto" : "none",
                transform: `translateX(calc(var(--off) * var(--peek))) translateY(${
                  isActive ? 0 : SIDE_DROP
                }px) scale(${isActive ? 1 : SIDE_SCALE})`,
                opacity: isActive ? 1 : isNeighbour ? SIDE_OPACITY : 0,
                transition,
              } as React.CSSProperties
            }
          >
            <div className="mx-auto w-[86%] sm:w-[66%]">{panel}</div>
          </div>
        );
      })}
    </div>
  );
}
