"use client";

import React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export type OnboardingStageProps = {
  /** Index of the active step. */
  current: number;
  /** +1 when moving forward, -1 when moving back. Drives slide direction. */
  direction: number;
  /** The rendered step panels, one per step. */
  steps: React.ReactNode[];
  className?: string;
};

// How much the peek panel is offset from its natural right-edge position.
// This value is percentage of the stage width to keep it responsive.
const PEEK_OFFSET_PERCENT = 82; // peek panel starts at 82% of stage width
const PEEK_SCALE = 0.92;
const PEEK_OPACITY = 0.35;

const SLIDE_DURATION = 0.6;
const SLIDE_EASE = [0.32, 0.01, 0.12, 1.0] as const; // slow organic cubic

// Variants for the animated active panel.
// `custom` receives the direction number (+1 / -1).
const panelVariants = {
  enter: (dir: number) => ({
    x: dir >= 0 ? "100%" : "-100%",
    opacity: 0,
  }),
  center: {
    x: "0%",
    opacity: 1,
  },
  exit: (dir: number) => ({
    x: dir >= 0 ? "-100%" : "100%",
    opacity: 0,
  }),
};

const panelTransition = {
  duration: SLIDE_DURATION,
  ease: SLIDE_EASE,
};

export default function OnboardingStage({
  current,
  direction,
  steps,
  className,
}: OnboardingStageProps) {
  const shouldReduceMotion = useReducedMotion();

  const activeStep = steps[current];
  const nextStep = current < steps.length - 1 ? steps[current + 1] : null;
  const hasPeek = nextStep !== null;

  if (shouldReduceMotion) {
    // Reduced-motion: crossfade only, no peek.
    return (
      <div
        className={cn("relative w-full overflow-hidden", className)}
      >
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={current}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="w-full"
          >
            {activeStep}
          </motion.div>
        </AnimatePresence>
      </div>
    );
  }

  return (
    // Outer wrapper clips overflow so peeking panel doesn't break page layout.
    <div
      className={cn("relative w-full overflow-hidden", className)}
      // Enough height clearance; children control their own height.
    >
      {/*
        Inner container is wider than 100% so the peek panel can be positioned
        partially off-screen to the right without creating horizontal scroll —
        the outer overflow-hidden clips it.
      */}
      <div className="relative w-full">
        {/* Active step panel — slides in/out */}
        <AnimatePresence mode="popLayout" custom={direction}>
          <motion.div
            key={current}
            custom={direction}
            variants={panelVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={panelTransition}
            className="w-full"
            // Active panel is fully interactive.
            aria-hidden={false}
          >
            {activeStep}
          </motion.div>
        </AnimatePresence>

        {/* Peeking next-step panel — positioned off the right edge */}
        {hasPeek && (
          <motion.div
            key={`peek-${current}`}
            // Sit in absolute position off to the right, partially visible.
            className="pointer-events-none absolute inset-y-0 w-full"
            style={{ left: `${PEEK_OFFSET_PERCENT}%` }}
            initial={{ opacity: 0, scale: PEEK_SCALE, x: "8%" }}
            animate={{ opacity: PEEK_OPACITY, scale: PEEK_SCALE, x: "0%" }}
            exit={{ opacity: 0, scale: PEEK_SCALE - 0.04, x: "6%" }}
            transition={{
              duration: SLIDE_DURATION,
              ease: SLIDE_EASE,
            }}
            // Accessibility: hidden from SR and keyboard navigation.
            aria-hidden={true}
            // pointer-events-none is already on className; belt-and-suspenders
            // tabIndex management is handled by aria-hidden + pointer-events-none
            // on the wrapper, so child focusables are unreachable in practice
            // (browsers skip aria-hidden subtrees for AT; pointer-events-none
            // prevents mouse activation).
            inert
          >
            <div className="h-full w-full overflow-hidden opacity-100">
              {nextStep}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
