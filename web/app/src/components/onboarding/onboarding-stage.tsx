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

// A simple horizontal slide: the active card sits centred and crisp; every
// other card slides straight out to its side and fades fully away so nothing
// lingers over the controls beneath. Tune these to taste.
const SLIDE_EASE = "cubic-bezier(0.32, 0.01, 0.12, 1)";
const SLIDE_MS = 460;

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
    // overflow-hidden clips the sliding cards so an outgoing card never bleeds
    // past the stage onto the controls beneath it.
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
                zIndex: isActive ? 30 : 10,
                pointerEvents: isActive ? "auto" : "none",
                // Each card slides one full stage-width per step; only the
                // active one is visible — the rest fade completely to nothing.
                transform: "translateX(calc(var(--off) * 100%))",
                opacity: isActive ? 1 : 0,
                transition,
              } as React.CSSProperties
            }
          >
            <div className="mx-auto w-full">{panel}</div>
          </div>
        );
      })}
    </div>
  );
}
