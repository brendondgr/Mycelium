import * as React from "react";

import { cn } from "@/lib/utils";

/** Percent-match tiers: strong (green), fair (amber), low (terracotta). */
const STRONG_MATCH = 85;
const FAIR_MATCH = 60;

/** Resolve a percent into a fit tier and its semantic color token + word. */
export function matchTier(percent: number): { token: string; word: string } {
  if (percent >= STRONG_MATCH) return { token: "--success", word: "strong" };
  if (percent >= FAIR_MATCH) return { token: "--warning", word: "fair" };
  return { token: "--clay", word: "low" };
}

type Size = "sm" | "md";

const RING: Record<Size, { box: string; track: string; text: string }> = {
  // Dense panels (overview lists) — number only, no caption.
  sm: { box: "h-9 w-9", track: "inset-[3px]", text: "text-[11px]" },
  // Feed cards — the card's left gutter.
  md: { box: "h-14 w-14", track: "inset-[5px]", text: "text-sm" },
};

/**
 * The percent match, drawn as a filled arc around the number.
 *
 * This is the one element that says "how well does this fit me", used
 * everywhere a percent is shown — papers, grants, conferences, fellowship
 * research fit, and the overview panels. The arc is a conic gradient swept to
 * the percent and colored by tier; the number sits inside it and the tier word
 * sits beneath, so fit is never carried by color alone.
 *
 * When Mylo (the language model) made the judgement rather than the
 * deterministic scorer, his portrait sits on the ring as attribution.
 *
 * A null percent renders nothing — the cross-embedding tail has no percent to
 * show and should not be given a fake one.
 */
export function MatchRing({
  percent,
  origin,
  size = "md",
  caption = true,
  className,
}: {
  percent: number | null | undefined;
  origin?: "llm" | "fallback" | "rules";
  size?: Size;
  /** Show the "strong/fair/low match" line beneath the ring. */
  caption?: boolean;
  className?: string;
}) {
  if (typeof percent !== "number" || !Number.isFinite(percent)) return null;

  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  const { token, word } = matchTier(pct);
  const byMylo = origin === "llm";
  const dims = RING[size];

  return (
    <div
      className={cn("flex shrink-0 flex-col items-center gap-1", className)}
      role="img"
      aria-label={`${pct} percent match to your research profile — a ${word} match${
        byMylo ? ", judged by Mylo" : ""
      }`}
    >
      <div className={cn("relative", dims.box)}>
        <div
          className="h-full w-full rounded-full"
          style={{
            background: `conic-gradient(var(${token}) ${pct}%, color-mix(in srgb, var(--border) 70%, transparent) 0)`,
          }}
        />
        <div
          className={cn(
            "absolute rounded-full bg-[var(--surface)]",
            dims.track,
          )}
        />
        <span
          className={cn(
            "absolute inset-0 flex items-center justify-center font-semibold tabular-nums text-[var(--text-primary)]",
            dims.text,
          )}
        >
          {pct}%
        </span>

        {byMylo && size === "md" ? (
          /* Attribution rides the ring rather than taking a row of its own. */
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src="/images/mylo-portrait-64.webp"
            alt=""
            width={20}
            height={20}
            className="absolute -bottom-0.5 -right-0.5 h-5 w-5 rounded-full object-cover ring-2 ring-[var(--surface)]"
          />
        ) : null}
      </div>

      {caption && size === "md" ? (
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          {word} match
        </span>
      ) : null}
    </div>
  );
}
