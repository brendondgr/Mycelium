"use client";

import * as React from "react";

import { MyloHead } from "./mylo-head";

/**
 * Mylo's painted head, fixed at the bottom right of every signed-in page.
 * Opens the panel on the last conversation, or a new one. Hidden while the
 * panel is open.
 */
export const Launcher = React.forwardRef<
  HTMLButtonElement,
  { onOpen: () => void; hidden: boolean }
>(function Launcher({ onOpen, hidden }, ref) {
  if (hidden) return null;
  return (
    <button
      ref={ref}
      type="button"
      className="ws-mylo-launcher"
      onClick={onOpen}
      aria-label="Ask Mylo"
      title="Ask Mylo"
    >
      <MyloHead size={46} />
    </button>
  );
});
