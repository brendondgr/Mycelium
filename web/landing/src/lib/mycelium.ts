/**
 * Mycelium threads and spores, grown at build time.
 *
 * A seeded random walk, so every build draws the same network and the browser
 * receives finished SVG paths — no runtime cost, no layout shift.
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

export type Thread = { d: string; tip: [number, number]; depth: number };

export type Spore = {
  left: string;
  bottom: string;
  size: string;
  dur: string;
  delay: string;
  gold: boolean;
};

/**
 * Threads rising from the bottom edge of a `width` × `height` box. They grow
 * taller toward the edges and stay low in the middle, where copy sits.
 */
export function growThreads(seed: number, width = 1440, height = 900, roots = 15): Thread[] {
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

/** Spores for a CSS drift animation, positioned in percent of their box. */
export function scatterSpores(seed: number, count: number, maxBottom = 60): Spore[] {
  const rand = prng(seed);
  return Array.from({ length: count }, () => ({
    left: (rand() * 100).toFixed(1),
    bottom: (rand() * maxBottom).toFixed(1),
    size: (1.5 + rand() * 2.5).toFixed(1),
    dur: (14 + rand() * 12).toFixed(1),
    delay: (-rand() * 20).toFixed(1),
    gold: rand() < 0.22,
  }));
}
