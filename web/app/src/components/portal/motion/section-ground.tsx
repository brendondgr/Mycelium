"use client";

import * as React from "react";

import { usePrefersReducedMotion } from "@/components/portal/motion/use-reduced-motion";

/**
 * A quiet botanical ground behind the workspace, keyed to the section you are
 * in — the public site's motif idea, dialled down for a surface people work in
 * all day.
 *
 * Three things keep it on the right side of the line the style guide draws
 * ("the interface should carry the work; do not let the motif compete"):
 *
 *   - It is *fixed* behind the scroll container, not repeated per section, so
 *     it never tiles down a long feed. It does respond to the scroll — the
 *     growth advances with your position in the feed — but slowly, over the
 *     whole length of it, and it is perfectly still whenever you are.
 *   - It is roughly a third of the strength of the marketing version, drawn
 *     only in the outer margins, and masked away from the middle of the page
 *     where the cards and their text actually live.
 *   - Each area gets its own growth, so Papers and Grants are distinguishable
 *     at a glance the way the marketing pages are — but a section with no entry
 *     here simply renders nothing rather than falling back to a default.
 *
 * Purely decorative: `aria-hidden`, no pointer events, and nothing here encodes
 * information that is not already in the page.
 */

type Growth = "roots" | "vine" | "canopy" | "spores";

/** Which growth belongs to which workspace area. */
const BY_SECTION: Record<string, Growth> = {
  "research-papers": "roots",
  suggested: "roots",
  grants: "spores",
  fellowships: "vine",
  conferences: "canopy",
  saves: "spores",
  overview: "vine",
  daily: "canopy",
};

/** Pull the area name out of `/app/<area>` (and `/app/labs/<slug>/<area>`). */
export function areaFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  const afterApp = parts[0] === "app" ? parts.slice(1) : parts;
  if (afterApp[0] === "labs" && afterApp.length >= 3) return afterApp[2];
  return afterApp[0] ?? "";
}

function Art({ growth }: { growth: Growth }) {
  if (growth === "roots") {
    return (
      <svg
        className="portal-ground-art"
        viewBox="0 0 1200 400"
        preserveAspectRatio="xMidYMin meet"
        fill="none"
      >
        <g className="portal-ground-line">
          <path d="M120 -20 C 120 60, 100 90, 98 140 C 96 190, 78 210, 70 264" pathLength={1} />
          <path d="M70 264 C 100 200, 130 190, 152 236" strokeWidth={1} pathLength={1} />
          <path d="M1080 -20 C 1082 62, 1102 88, 1106 138 C 1110 188, 1094 212, 1088 266" pathLength={1} />
          <path d="M1088 266 C 1058 202, 1030 190, 1010 232" strokeWidth={1} pathLength={1} />
        </g>
        <g className="portal-ground-node">
          <circle cx="70" cy="264" r="3" />
          <circle cx="152" cy="236" r="2.2" />
          <circle cx="1088" cy="266" r="3" />
          <circle cx="1010" cy="232" r="2.2" />
        </g>
      </svg>
    );
  }

  if (growth === "vine") {
    return (
      <svg
        className="portal-ground-art"
        viewBox="0 0 1200 900"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
      >
        <defs>
          <path id="portal-leaf" d="M0 0 C 7 -9, 22 -9, 29 0 C 22 9, 7 9, 0 0 Z" />
        </defs>
        <g className="portal-ground-line">
          <path d="M78 -40 C 30 140, 110 320, 62 500 C 20 660, 96 780, 60 960" pathLength={1} />
          <path d="M1128 -40 C 1176 140, 1096 320, 1144 500 C 1186 660, 1110 780, 1146 960" pathLength={1} />
        </g>
        <g className="portal-ground-leaf">
          <use style={{ "--i": 0 } as React.CSSProperties} href="#portal-leaf" transform="translate(66 90) rotate(-34)" />
          <use style={{ "--i": 1 } as React.CSSProperties} href="#portal-leaf" transform="translate(52 300) rotate(196) scale(0.86)" />
          <use style={{ "--i": 2 } as React.CSSProperties} href="#portal-leaf" transform="translate(74 520) rotate(-22) scale(0.92)" />
          <use style={{ "--i": 3 } as React.CSSProperties} href="#portal-leaf" transform="translate(48 740) rotate(190) scale(0.8)" />
          <use style={{ "--i": 4 } as React.CSSProperties} href="#portal-leaf" transform="translate(1134 90) rotate(214)" />
          <use style={{ "--i": 5 } as React.CSSProperties} href="#portal-leaf" transform="translate(1148 300) rotate(-16) scale(0.86)" />
          <use style={{ "--i": 6 } as React.CSSProperties} href="#portal-leaf" transform="translate(1126 520) rotate(202) scale(0.92)" />
          <use style={{ "--i": 7 } as React.CSSProperties} href="#portal-leaf" transform="translate(1152 740) rotate(-10) scale(0.8)" />
        </g>
      </svg>
    );
  }

  if (growth === "canopy") {
    return (
      <svg
        className="portal-ground-art"
        viewBox="0 0 1200 300"
        preserveAspectRatio="xMidYMin meet"
        fill="none"
      >
        <defs>
          <path id="portal-canopy-leaf" d="M0 0 C 6 -9, 21 -9, 27 0 C 21 9, 6 9, 0 0 Z" />
        </defs>
        <g className="portal-ground-line">
          <path d="M-30 -10 C 90 22, 172 66, 236 140" pathLength={1} />
          <path d="M1230 -10 C 1110 22, 1028 66, 964 140" pathLength={1} />
        </g>
        <g className="portal-ground-leaf">
          <use style={{ "--i": 0 } as React.CSSProperties} href="#portal-canopy-leaf" transform="translate(44 0) rotate(26) scale(0.86)" />
          <use style={{ "--i": 1 } as React.CSSProperties} href="#portal-canopy-leaf" transform="translate(118 40) rotate(50) scale(0.76)" />
          <use style={{ "--i": 2 } as React.CSSProperties} href="#portal-canopy-leaf" transform="translate(186 96) rotate(66) scale(0.7)" />
          <use style={{ "--i": 3 } as React.CSSProperties} href="#portal-canopy-leaf" transform="translate(1156 0) rotate(154) scale(0.86)" />
          <use style={{ "--i": 4 } as React.CSSProperties} href="#portal-canopy-leaf" transform="translate(1082 40) rotate(130) scale(0.76)" />
          <use style={{ "--i": 5 } as React.CSSProperties} href="#portal-canopy-leaf" transform="translate(1014 96) rotate(114) scale(0.7)" />
        </g>
      </svg>
    );
  }

  return (
    <svg
      className="portal-ground-art"
      viewBox="0 0 1200 900"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
    >
      <g className="portal-ground-node">
        <circle style={{ "--i": 1.0 } as React.CSSProperties} cx="64" cy="120" r="4" />
        <circle style={{ "--i": 0.6 } as React.CSSProperties} cx="128" cy="316" r="2.6" />
        <circle style={{ "--i": 0.85 } as React.CSSProperties} cx="52" cy="520" r="3.4" />
        <circle style={{ "--i": 0.45 } as React.CSSProperties} cx="116" cy="742" r="2.4" />
        <circle style={{ "--i": 1.15 } as React.CSSProperties} cx="1140" cy="150" r="3.6" />
        <circle style={{ "--i": 0.5 } as React.CSSProperties} cx="1074" cy="352" r="2.4" />
        <circle style={{ "--i": 0.95 } as React.CSSProperties} cx="1152" cy="566" r="4" />
        <circle style={{ "--i": 0.7 } as React.CSSProperties} cx="1088" cy="786" r="2.8" />
      </g>
    </svg>
  );
}

/**
 * Ties the growth to how far down the feed the reader has come.
 *
 * The public site can hand this to a scroll-driven CSS animation, because
 * there each ground travels the viewport with its own section. Here the ground
 * is deliberately fixed behind a scrolling panel, so there is nothing for a
 * `view()` timeline to measure — the progress is written from the container's
 * own scroll position instead. It is a ratio of the whole feed, so the growth
 * advances over hundreds of pixels: roots reaching further down, leaves opening
 * one at a time, spores drifting slowly up past the reader. Scrolling back up
 * runs it backwards.
 *
 * Under reduced motion nothing is written at all and the property keeps its
 * initial value of 1 — fully grown, perfectly still.
 */
function useScrollGrowth(reducedMotion: boolean) {
  const ref = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion) return;
    // The scroller is the sibling panel this ground sits behind.
    const scroller = el.parentElement?.querySelector("main");
    if (!scroller) return;

    let queued = false;
    const paint = () => {
      queued = false;
      const span = scroller.scrollHeight - scroller.clientHeight;
      const p = span > 0 ? scroller.scrollTop / span : 1;
      el.style.setProperty("--ground-progress", Math.min(1, Math.max(0, p)).toFixed(4));
      // Enables the displacement half of the effect; without a driver the
      // ground renders composed and undisplaced rather than at one extreme.
      el.style.setProperty("--ground-driven", "1");
    };
    const schedule = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(paint);
    };

    schedule();
    scroller.addEventListener("scroll", schedule, { passive: true });
    // The feed grows as slices load, which changes the denominator.
    const ro = new ResizeObserver(schedule);
    ro.observe(scroller);
    if (scroller.firstElementChild) ro.observe(scroller.firstElementChild);

    return () => {
      scroller.removeEventListener("scroll", schedule);
      ro.disconnect();
    };
  }, [reducedMotion]);

  return ref;
}

export function PortalGround({ pathname }: { pathname: string }) {
  const reducedMotion = usePrefersReducedMotion();
  const ref = useScrollGrowth(reducedMotion);
  const growth = BY_SECTION[areaFromPath(pathname)];
  if (!growth) return null;
  return (
    <div ref={ref} className="portal-ground" aria-hidden="true">
      <Art growth={growth} />
    </div>
  );
}
