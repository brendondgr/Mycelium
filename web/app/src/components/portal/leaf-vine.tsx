"use client";

import * as React from "react";

import { usePrefersReducedMotion } from "@/components/portal/motion/use-reduced-motion";

/**
 * A decorative "growing vine" that traces a sidebar row's pill and sprouts
 * leaves along its top edge when the row is hovered, focused, or active. Ported
 * from the Leaf Nav design proposal, re-parameterised to the row's real pixel
 * size (measured, so leaves never shear) and coloured from the Mycelium tokens
 * rather than fixed hex.
 *
 * It is purely ornamental: `aria-hidden`, non-interactive, and it renders
 * nothing under `prefers-reduced-motion: reduce`, where the row's tint, heavier
 * label, and `aria-current` are the (motion-free) state signal instead.
 */
type LeafVineProps = {
  /** Row is hovered, focused, or active — grow the vine + leaves in. */
  grown: boolean;
  /** Row is the current page — adds the slow "breeze" sway. */
  active: boolean;
  /** How many leaves to sprout. */
  leafCount?: number;
  /** Animation speed multiplier; < 1 is slower/calmer. */
  speed?: number;
  /**
   * Corner radius of the box being traced. Defaults to the sidebar row's 10px;
   * pass half the height for a `rounded-full` pill such as the search field, or
   * the vine will cut across its corners.
   */
  radius?: number;
};

/** The single leaf outline, drawn around its stem base at (0,0), pointing up. */
const LEAF_D = "M0 0 C4.5 -3.5 6 -10 0.5 -15 C-5 -10 -4 -3.5 0 0 Z";

/** Watch an element's border-box size. Falls back to a stable default for SSR. */
function useElementSize<T extends Element>(): [React.RefObject<T | null>, { w: number; h: number }] {
  const ref = React.useRef<T | null>(null);
  const [size, setSize] = React.useState({ w: 216, h: 40 });
  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box && box.width > 0 && box.height > 0) {
        setSize((prev) =>
          prev.w === box.width && prev.h === box.height
            ? prev
            : { w: box.width, h: box.height },
        );
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size];
}

/** Hand-drawn path tracing the rounded border of a `w`×`h` box at radius `r`. */
function buildStemPath(w: number, h: number, r: number): string {
  const ins = 1.5;
  const raw: Array<[number, number]> = [];
  const arc = (cx: number, cy: number, a0: number, a1: number) => {
    for (let s = 0; s <= 4; s++) {
      const a = a0 + ((a1 - a0) * s) / 4;
      raw.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
    }
  };
  for (let x = ins + r; x <= w - ins - r; x += 9) raw.push([x, ins]);
  arc(w - ins - r, ins + r, -Math.PI / 2, 0);
  for (let y = ins + r; y <= h - ins - r; y += 9) raw.push([w - ins, y]);
  arc(w - ins - r, h - ins - r, 0, Math.PI / 2);
  for (let x = w - ins - r; x >= ins + r; x -= 9) raw.push([x, h - ins]);
  arc(ins + r, h - ins - r, Math.PI / 2, Math.PI);
  for (let y = h - ins - r; y >= ins + r; y -= 9) raw.push([ins, y]);
  arc(ins + r, ins + r, Math.PI, Math.PI * 1.5);
  const pts = raw.map(
    (p, k) =>
      `${(p[0] + 0.55 * Math.sin(k * 1.3)).toFixed(1)} ${(p[1] + 0.55 * Math.cos(k * 1.7)).toFixed(1)}`,
  );
  return `M${pts.join(" L")} Z`;
}

export function LeafVine({
  grown,
  active,
  leafCount = 8,
  speed = 0.5,
  radius = 10,
}: LeafVineProps) {
  const [ref, { w, h }] = useElementSize<HTMLDivElement>();
  const reducedMotion = usePrefersReducedMotion();

  // Never let the radius exceed half the shorter side, or the arcs cross over
  // each other and the "pill" folds inside out.
  const r = Math.max(0, Math.min(radius, Math.min(w, h) / 2));
  const stemD = React.useMemo(() => buildStemPath(w, h, r), [w, h, r]);
  const n = Math.max(1, leafCount);
  // Perimeter upper bound (rounded corners only shorten it) — a safe dash length
  // so the stroke fully hides at offset=dash and fully draws at offset=0.
  const dash = Math.round(2 * (w + h));

  if (reducedMotion) return null;

  const leaves = Array.from({ length: n }, (_, i) => {
    const t = n === 1 ? 0 : i / (n - 1);
    const x = 24 + t * (w - 48);
    const y = 2.5;
    const ang = 180 + (i % 2 ? 9 : -11) + ((i * 37) % 9) - 4;
    const sc = 0.5 + ((i * 29) % 14) / 100;
    const delay = grown ? (60 + t * 400) / speed : ((1 - t) * 140) / speed;
    return (
      <path
        key={i}
        d={LEAF_D}
        fill="var(--primary)"
        style={{
          transform: `translate(${x}px,${y}px) rotate(${ang}deg) scale(${grown ? sc : 0})`,
          transformOrigin: "0px 0px",
          fillOpacity: i % 2 ? 0.78 : 0.95,
          transition: `transform ${(0.45 / speed).toFixed(2)}s cubic-bezier(.28,1.25,.5,1) ${delay.toFixed(0)}ms`,
        }}
      />
    );
  });

  return (
    <div ref={ref} aria-hidden className="pointer-events-none absolute inset-0 z-[1]">
      <svg
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className={active ? "leaf-vine-breeze" : undefined}
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          overflow: "visible",
          transformOrigin: "50% 0",
        }}
      >
        <path
          d={stemD}
          fill="none"
          stroke="var(--primary)"
          strokeWidth={1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            strokeDasharray: dash,
            strokeDashoffset: grown ? 0 : dash,
            transition: `stroke-dashoffset ${((grown ? 1.0 : 0.5) / speed).toFixed(2)}s ease`,
          }}
        />
        <g>{leaves}</g>
      </svg>
    </div>
  );
}
