"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export type StatCardProps = {
  icon: React.ReactNode;
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  onClick?: () => void;
  /** Content alignment. Defaults to "left"; "center" horizontally centers the
   * icon/label row, the value, and the sub line (used by the Daily summaries). */
  align?: "left" | "center";
};

/**
 * A compact metric card for the overview stat grid. Renders as a button when
 * `onClick` is provided so it's keyboard and screen-reader accessible. The
 * large serif value defaults to "—" when the data is missing.
 */
export function StatCard({
  icon,
  label,
  value,
  sub,
  onClick,
  align = "left",
}: StatCardProps) {
  const centered = align === "center";
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-2xl border border-border bg-surface shadow-[var(--shadow)] p-[18px] w-full",
        centered ? "text-center" : "text-left",
        "transition-transform motion-safe:hover:-translate-y-0.5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        !onClick && "cursor-default",
      )}
    >
      <RootLine />

      {/* Icon + label row */}
      <div
        className={cn(
          "relative flex items-center gap-2 mb-3 text-[var(--text-secondary)]",
          centered && "justify-center",
        )}
      >
        <span className="text-primary">{icon}</span>
        <span className="text-[12.5px] font-medium">{label}</span>
      </div>

      {/* Big value */}
      <div className="relative font-serif text-[30px] font-semibold leading-none mb-[5px] text-[var(--text-primary)]">
        {value !== null && value !== undefined ? value : "—"}
      </div>

      {/* Muted sub line */}
      {sub && (
        <div className="relative text-[12px] text-[var(--text-secondary)]">
          {sub}
        </div>
      )}
    </button>
  );
}

/**
 * A mycelium line that draws itself across the card's background on hover or
 * keyboard focus, beneath the content.
 *
 * Kept at ~14% opacity: this is connective tissue, not a chart, and it must
 * never fight the value sitting on top of it. Only `stroke-dashoffset`,
 * `transform`, and `opacity` move, so nothing here can reflow the card, and the
 * transitions live inside the reduced-motion guard in `globals.css` — without
 * them the line simply stays retracted and the card behaves exactly as before.
 */
function RootLine() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 200 80"
      preserveAspectRatio="none"
      fill="none"
      className="mycelium-root-line pointer-events-none absolute inset-0 h-full w-full opacity-[0.14]"
    >
      {[
        {
          d: "M10 74 C10 62 20 56 36 51 C56 45 76 40 96 33 C118 25 142 19 172 15",
          w: 1.6,
        },
        { d: "M36 51 C50 55 60 61 68 70", w: 1 },
        { d: "M96 33 C110 37 120 44 127 54", w: 1 },
      ].map((seg) => (
        <path
          key={seg.d}
          d={seg.d}
          pathLength={100}
          stroke="var(--primary)"
          strokeWidth={seg.w}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          className="[stroke-dashoffset:100] group-hover:[stroke-dashoffset:0] group-focus-visible:[stroke-dashoffset:0]"
          style={{ strokeDasharray: 100 }}
        />
      ))}
      {[
        { cx: 68, cy: 70, r: 1.8 },
        { cx: 127, cy: 54, r: 1.8 },
        { cx: 172, cy: 15, r: 2.4 },
      ].map((node) => (
        <ellipse
          key={`${node.cx}-${node.cy}`}
          cx={node.cx}
          cy={node.cy}
          rx={node.r}
          ry={node.r}
          fill="var(--primary)"
          className="origin-center scale-0 opacity-0 group-hover:scale-100 group-hover:opacity-100 group-focus-visible:scale-100 group-focus-visible:opacity-100"
          style={{ transformBox: "fill-box" }}
        />
      ))}
    </svg>
  );
}
