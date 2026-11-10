"use client";

import * as React from "react";

import { useDemo } from "@/components/demo/demo-context";
import { DEMO_REFUSED_EVENT } from "@/lib/demo";

/**
 * The strip above the workspace in the public demo: what this is, and the way
 * out. When the demo refuses a change (every save, edit or invite is refused
 * at the API), the strip says so for a few seconds, so a button that does
 * nothing is never a mystery. Renders nothing outside the demo.
 */
export function DemoBanner() {
  const demo = useDemo();
  const [refused, setRefused] = React.useState(false);

  React.useEffect(() => {
    if (!demo) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onRefused = () => {
      setRefused(true);
      clearTimeout(timer);
      timer = setTimeout(() => setRefused(false), 5000);
    };
    window.addEventListener(DEMO_REFUSED_EVENT, onRefused);
    return () => {
      window.removeEventListener(DEMO_REFUSED_EVENT, onRefused);
      clearTimeout(timer);
    };
  }, [demo]);

  if (!demo) return null;
  return (
    <div className="ws-demo-banner" data-refused={refused || undefined} role="region" aria-label="Demo">
      <p aria-live="polite">
        <span className="ws-demo-tag">Demo</span>
        {refused
          ? "This is a demo, so nothing here can be changed."
          : "A fictional lab, ranked last night against real papers, grants and calls."}
      </p>
      <p>
        <a href="/signup">Sign up</a> to set up your own ·{" "}
        {/* "/" is the public site, which nginx serves, not a page of this app. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/">Leave the demo</a>
      </p>
    </div>
  );
}
