import * as React from "react";

/**
 * The workspace background: a field-map contour, ported from the `/labs`
 * playground where it was chosen over a blank page (35 % strength).
 *
 * The rings are computed from a fixed seed, so server and client draw the same
 * paths and nothing shifts on hydration. It is fixed behind the scroll area —
 * it never tiles down a long feed — masked mostly out of the centre band where
 * the text sits, and entirely still: `aria-hidden`, no pointer events, and it
 * encodes nothing that is not already on the page.
 */

function prng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Closed, gently wobbling rings around two centres. */
function contours(seed: number): string[] {
  const rand = prng(seed);
  const paths: string[] = [];
  const centres: [number, number][] = [
    [180, 760],
    [1300, 160],
  ];
  for (const [cx, cy] of centres) {
    const phase = rand() * Math.PI * 2;
    for (let ring = 1; ring <= 9; ring++) {
      const r = ring * 58;
      const pts: string[] = [];
      for (let a = 0; a <= 64; a++) {
        const t = (a / 64) * Math.PI * 2;
        const wobble = 1 + 0.09 * Math.sin(3 * t + phase + ring * 0.4) + 0.05 * Math.sin(5 * t - phase);
        pts.push(
          `${(cx + Math.cos(t) * r * wobble * 1.25).toFixed(1)} ${(cy + Math.sin(t) * r * wobble).toFixed(1)}`,
        );
      }
      paths.push(`M${pts.join(" L")} Z`);
    }
  }
  return paths;
}

const RINGS = contours(11);

export function WorkspaceGround() {
  return (
    <div className="ws-ground" aria-hidden="true">
      <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
        <g className="ws-contour">
          {RINGS.map((d, i) => (
            <path key={i} d={d} />
          ))}
        </g>
      </svg>
    </div>
  );
}
