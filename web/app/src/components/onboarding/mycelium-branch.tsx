"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export type MyceliumBranchProps = {
  /** Total number of steps. */
  steps: number;
  /** 0-based index of the active step. */
  current: number;
  className?: string;
};

// Generate a gently curved cubic-bezier path through `count` evenly-spaced
// points along the SVG width, with a subtle organic S-curve.
function buildMainPath(count: number, width: number, cy: number): string {
  if (count < 2) return `M 0 ${cy} L ${width} ${cy}`;
  const points = Array.from({ length: count }, (_, i) => ({
    x: (i / (count - 1)) * width,
    y: cy + (i % 2 === 0 ? -4 : 4), // subtle vertical weave
  }));
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    const cpx = (prev.x + cur.x) / 2;
    d += ` C ${cpx} ${prev.y} ${cpx} ${cur.y} ${cur.x} ${cur.y}`;
  }
  return d;
}

// Generate a short side-filament path from a node point. `wobble` is a
// deterministic per-filament curve offset (kept out of Math.random so server
// and client render identically — no hydration mismatch).
function filamentPath(
  x: number,
  y: number,
  angle: number,
  length: number,
  wobble: number,
): string {
  const ex = x + Math.cos(angle) * length;
  const ey = y + Math.sin(angle) * length;
  const cpx = x + Math.cos(angle) * length * 0.5;
  const cpy = y + Math.sin(angle) * length * 0.5 + wobble;
  return `M ${x} ${y} Q ${cpx} ${cpy} ${ex} ${ey}`;
}

// Pre-computed filament descriptors so they're stable across renders. `wobble`
// is a fixed per-filament control-point offset (deterministic, not random).
const FILAMENTS = [
  { nodeIndex: 0, angle: -Math.PI / 4, length: 18, wobble: 4 },
  { nodeIndex: 0, angle: Math.PI / 3.5, length: 14, wobble: -4 },
  { nodeIndex: 1, angle: -Math.PI / 5, length: 20, wobble: 4 },
  { nodeIndex: 2, angle: Math.PI / 4, length: 16, wobble: -4 },
  { nodeIndex: 2, angle: -Math.PI / 3, length: 12, wobble: 4 },
  { nodeIndex: 3, angle: Math.PI / 3.5, length: 22, wobble: -4 },
  { nodeIndex: 3, angle: -Math.PI / 5, length: 15, wobble: 4 },
  { nodeIndex: 4, angle: Math.PI / 4, length: 18, wobble: -4 },
];

const VIEW_WIDTH = 480;
const VIEW_HEIGHT = 56;
const CY = VIEW_HEIGHT / 2;
const GLOW_R = 9;
const NODE_R_ACTIVE = 6;
const NODE_R_REACHED = 5;
const NODE_R_FUTURE = 3.5;

export default function MyceliumBranch({
  steps,
  current,
  className,
}: MyceliumBranchProps) {
  const shouldReduceMotion = useReducedMotion();
  const effectiveSteps = Math.max(2, steps);
  const clampedCurrent = Math.max(0, Math.min(current, effectiveSteps - 1));

  const mainPath = buildMainPath(effectiveSteps, VIEW_WIDTH, CY);

  // Fraction of the path that is "grown" (0 → 1 over steps).
  const grownFraction =
    effectiveSteps > 1 ? clampedCurrent / (effectiveSteps - 1) : 1;

  // Node positions along the path.
  const nodes = Array.from({ length: effectiveSteps }, (_, i) => {
    const nx = (i / (effectiveSteps - 1)) * VIEW_WIDTH;
    const ny = CY + (i % 2 === 0 ? -4 : 4);
    return { x: nx, y: ny };
  });

  return (
    <svg
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      width="100%"
      className={cn("overflow-visible", className)}
      aria-hidden="true"
      role="presentation"
    >
      {/* Faint full-path underlay (future, always drawn) */}
      <path
        d={mainPath}
        stroke="var(--border)"
        strokeWidth="1.5"
        strokeDasharray="4 5"
        fill="none"
        opacity="0.5"
      />

      {/* Grown portion of the main branch (animated pathLength) */}
      {shouldReduceMotion ? (
        <path
          d={mainPath}
          stroke="var(--brand-secondary)"
          strokeWidth="2"
          fill="none"
          strokeDasharray="1 0"
          style={{ pathLength: grownFraction } as React.CSSProperties}
        />
      ) : (
        <motion.path
          d={mainPath}
          stroke="var(--brand-secondary)"
          strokeWidth="2"
          fill="none"
          initial={{ pathLength: 0, opacity: 0.6 }}
          animate={{ pathLength: grownFraction, opacity: 1 }}
          transition={{
            pathLength: { duration: 0.9, ease: "easeInOut" },
            opacity: { duration: 0.3 },
          }}
        />
      )}

      {/* Side filaments — decorative mycelium threads */}
      {FILAMENTS.filter((f) => f.nodeIndex < effectiveSteps).map((f, fi) => {
        const node = nodes[f.nodeIndex];
        if (!node) return null;
        const isReached = f.nodeIndex <= clampedCurrent;
        return (
          <path
            key={fi}
            d={filamentPath(node.x, node.y, f.angle, f.length, f.wobble)}
            stroke="var(--brand-secondary)"
            strokeWidth="1"
            fill="none"
            opacity={isReached ? 0.4 : 0.15}
            strokeLinecap="round"
          />
        );
      })}

      {/* Nodes */}
      {nodes.map((node, i) => {
        const isActive = i === clampedCurrent;
        const isReached = i < clampedCurrent;
        const isFuture = i > clampedCurrent;

        const r = isActive ? NODE_R_ACTIVE : isReached ? NODE_R_REACHED : NODE_R_FUTURE;
        const fill = isFuture ? "var(--surface)" : "var(--primary)";
        const stroke = isFuture ? "var(--border)" : "var(--brand-secondary)";
        const opacity = isFuture ? 0.45 : 1;

        if (shouldReduceMotion) {
          return (
            <g key={i}>
              {isActive && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={GLOW_R}
                  fill="var(--brand-accent)"
                  opacity="0.25"
                />
              )}
              <circle
                cx={node.x}
                cy={node.y}
                r={r}
                fill={fill}
                stroke={stroke}
                strokeWidth="1.5"
                opacity={opacity}
              />
            </g>
          );
        }

        return (
          <motion.g
            key={i}
            initial={
              isReached || isActive
                ? { scale: 0.6, opacity: 0 }
                : { scale: 1, opacity: 1 }
            }
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.45, ease: "easeOut", delay: i === clampedCurrent ? 0.4 : 0 }}
            style={{ originX: `${node.x}px`, originY: `${node.y}px` }}
          >
            {/* Glow ring on active node */}
            {isActive && (
              <motion.circle
                cx={node.x}
                cy={node.y}
                r={GLOW_R}
                fill="var(--brand-accent)"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 0.28, scale: 1 }}
                transition={{ duration: 0.55, ease: "easeOut", delay: 0.5 }}
                style={{ originX: `${node.x}px`, originY: `${node.y}px` }}
              />
            )}
            <circle
              cx={node.x}
              cy={node.y}
              r={r}
              fill={fill}
              stroke={stroke}
              strokeWidth="1.5"
              opacity={opacity}
            />
          </motion.g>
        );
      })}
    </svg>
  );
}
