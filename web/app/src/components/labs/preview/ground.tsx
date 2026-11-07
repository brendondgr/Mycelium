"use client";

import * as React from "react";

/**
 * The preview's background layer — the answer to "one blank background that
 * looks boring". Each variant is drawn once from a seed, so server and client
 * render the same paths and nothing shifts on hydration.
 *
 * The threads are the front page's own generator (`web/landing/src/lib/
 * mycelium.ts`), ported so the workspace and the hero grow the same network.
 * Every variant is aria-hidden, pointer-events: none, and masked out of the
 * centre band where text sits.
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

type Thread = { d: string; tip: [number, number]; depth: number };

function growThreads(seed: number, width = 1440, height = 900, roots = 15): Thread[] {
  const rand = prng(seed);
  const threads: Thread[] = [];

  function grow(x: number, y: number, angle: number, steps: number, depth: number) {
    const pts: [number, number][] = [[x, y]];
    for (let i = 0; i < steps; i++) {
      angle += (rand() - 0.5) * 0.55;
      angle = Math.max(-Math.PI + 0.35, Math.min(-0.35, angle));
      const len = 42 + rand() * 46;
      x += Math.cos(angle) * len;
      y += Math.sin(angle) * len;
      pts.push([x, y]);
      if (depth < 2 && i > 0 && i < steps - 1 && rand() < 0.32) {
        const turn = (rand() < 0.5 ? -1 : 1) * (0.5 + rand() * 0.4);
        grow(x, y, angle + turn, Math.max(2, steps - i - 1), depth + 1);
      }
    }
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const mx = (pts[i][0] + pts[i + 1][0]) / 2;
      const my = (pts[i][1] + pts[i + 1][1]) / 2;
      d += ` Q${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)} ${mx.toFixed(1)} ${my.toFixed(1)}`;
    }
    const last = pts[pts.length - 1];
    d += ` L${last[0].toFixed(1)} ${last[1].toFixed(1)}`;
    threads.push({ d, tip: last, depth });
  }

  for (let i = 0; i < roots; i++) {
    const x = 40 + ((width - 80) / (roots - 1)) * i + (rand() - 0.5) * 50;
    const edge = Math.abs(x - width / 2) / (width / 2);
    grow(x, height + 5, -Math.PI / 2 + (rand() - 0.5) * 0.5, 3 + Math.round(edge * 5 + rand() * 2), 0);
  }
  return threads;
}

/** Closed, gently wobbling rings around two centres — a field-map contour. */
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
        pts.push(`${(cx + Math.cos(t) * r * wobble * 1.25).toFixed(1)} ${(cy + Math.sin(t) * r * wobble).toFixed(1)}`);
      }
      paths.push(`M${pts.join(" L")} Z`);
    }
  }
  return paths;
}

function spores(seed: number, count: number) {
  const rand = prng(seed);
  return Array.from({ length: count }, () => ({
    left: (rand() * 100).toFixed(1),
    bottom: (rand() * 70).toFixed(1),
    size: (1.5 + rand() * 2.5).toFixed(1),
    dur: (16 + rand() * 14).toFixed(1),
    delay: (-rand() * 24).toFixed(1),
    gold: rand() < 0.22,
  }));
}

export function Ground({ variant }: { variant: string }) {
  const threads = React.useMemo(() => growThreads(20261107), []);
  const rings = React.useMemo(() => contours(11), []);
  const specks = React.useMemo(() => spores(5, 34), []);

  if (variant === "plain") return null;

  return (
    <div className="lx-ground" data-variant={variant} aria-hidden="true">
      {variant === "threads" ? (
        <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMax slice">
          <g className="lx-thread-base">
            {threads.map((t, i) => (
              <path
                key={i}
                d={t.d}
                pathLength={1}
                style={{ "--i": i, "--w": t.depth === 0 ? 1.5 : 0.9 } as React.CSSProperties}
              />
            ))}
          </g>
          <g className="lx-thread-pulse">
            {threads
              .filter((_, i) => i % 3 === 0)
              .map((t, i) => (
                <path key={i} d={t.d} pathLength={1} style={{ "--i": i } as React.CSSProperties} />
              ))}
          </g>
          <g className="lx-thread-tips">
            {threads
              .filter((t) => t.depth === 0)
              .map((t, i) => (
                <circle key={i} cx={t.tip[0]} cy={t.tip[1]} r={4} style={{ "--i": i } as React.CSSProperties} />
              ))}
          </g>
        </svg>
      ) : null}

      {variant === "contour" ? (
        <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
          <g className="lx-contour">
            {rings.map((d, i) => (
              <path key={i} d={d} />
            ))}
          </g>
        </svg>
      ) : null}

      {variant === "spores" ? (
        <div className="lx-spores">
          {specks.map((s, i) => (
            <span
              key={i}
              data-gold={s.gold || undefined}
              style={
                {
                  left: `${s.left}%`,
                  bottom: `${s.bottom}%`,
                  width: `${s.size}px`,
                  height: `${s.size}px`,
                  "--dur": `${s.dur}s`,
                  "--delay": `${s.delay}s`,
                } as React.CSSProperties
              }
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
