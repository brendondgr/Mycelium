"use client";

import * as React from "react";

/**
 * Cross-fades the active section into view. Remounting on `stageKey` change
 * restarts a short opacity-only fade (`ws-stage`), so a page — or its loading
 * placeholder — never slides or shifts as it arrives. Reduced motion and
 * Motion: None get an instant swap.
 */
export function SectionStage({
  stageKey,
  children,
}: {
  stageKey: string;
  children: React.ReactNode;
}) {
  return (
    <div key={stageKey} className="ws-stage h-full min-w-0">
      {children}
    </div>
  );
}
