"use client";

import * as React from "react";

import { useInViewOnce } from "@/components/portal/motion/use-in-view-once";
import { usePrefersReducedMotion } from "@/components/portal/motion/use-reduced-motion";
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
  // Feed cards — the notch at the card's top-left. Kept deliberately compact:
  // this block sets the notch height, so every pixel here is repeated down the
  // whole feed.
  md: { box: "h-12 w-12", track: "inset-[4px]", text: "text-[13px]" },
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
  scope,
  className,
}: {
  percent: number | null | undefined;
  origin?: "llm" | "fallback" | "rules";
  size?: Size;
  /** Show the "strong/fair/low match" line beneath the ring. */
  caption?: boolean;
  /**
   * Whose profile the percent is measured against, when it is not the reader's.
   * A lab feed ranks items against the *lab's* aggregate interests, and a card
   * that says nothing invites the number to be read as a personal one — on a
   * fellowship card it can sit beside two other percentages with three different
   * scopes. Pass the lab or project name.
   */
  scope?: string;
  className?: string;
}) {
  const reducedMotion = usePrefersReducedMotion();
  // The arc sweeps to its value the first time the ring is genuinely on screen,
  // so the number reads as measured rather than asserted. Once only: a feed of
  // twenty-five cards replaying on every scroll back would be nausea, not
  // polish. Hooks run before the null guard below, as they must.
  const [ringRef, swept] = useInViewOnce<HTMLDivElement>({ enabled: !reducedMotion });

  if (typeof percent !== "number" || !Number.isFinite(percent)) return null;

  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  const { token, word } = matchTier(pct);
  const byMylo = origin === "llm";
  const dims = RING[size];

  return (
    <div
      className={cn("flex shrink-0 flex-col items-center gap-1", className)}
      role="img"
      title={scope ? `${pct}% match to ${scope}` : undefined}
      aria-label={`${pct} percent match to ${
        scope ? `${scope}'s research profile` : "your research profile"
      } — a ${word} match${byMylo ? ", judged by Mylo" : ""}`}
    >
      <div ref={ringRef} className={cn("relative", dims.box)}>
        <div
          className={cn(
            "h-full w-full rounded-full",
            swept && "mycelium-ring-sweep",
          )}
          style={
            {
              // The percent lives in a registered custom property so the sweep
              // can interpolate it. Where @property is unsupported the ring
              // renders straight at its final value, which is the right
              // fallback — the number is the message, the sweep is the manner.
              "--ring-sweep": `${pct}%`,
              background: `conic-gradient(var(${token}) var(--ring-sweep), color-mix(in srgb, var(--border) 70%, transparent) 0)`,
            } as React.CSSProperties
          }
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
            src="/mylo-portrait-64.webp"
            alt=""
            width={20}
            height={20}
            className="absolute -bottom-0.5 -right-0.5 h-5 w-5 rounded-full object-cover ring-2 ring-[var(--surface)]"
          />
        ) : null}
      </div>

      {caption && size === "md" ? (
        /* Just the tier word. "strong match" needed two lines at the ring's
           width, and the second line only repeated what the ring already
           says — the aria-label still reads the full phrase. */
        <span className="text-[10px] font-semibold uppercase leading-none tracking-[0.06em] text-[var(--text-secondary)]">
          {word}
        </span>
      ) : null}
    </div>
  );
}
