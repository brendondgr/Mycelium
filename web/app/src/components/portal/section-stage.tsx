"use client";

import * as React from "react";

/**
 * Cross-fades the active section into view. Remounting on `stageKey` change
 * restarts the `portal-fade-up` entrance (a gentle fade + rise). The keyframe is
 * defined only under `prefers-reduced-motion: no-preference`, so reduced-motion
 * users get an instant, non-animated swap with no flash.
 */
export function SectionStage({
  stageKey,
  children,
}: {
  stageKey: string;
  children: React.ReactNode;
}) {
  return (
    <div key={stageKey} className="portal-fade-up h-full min-w-0">
      {children}
    </div>
  );
}
