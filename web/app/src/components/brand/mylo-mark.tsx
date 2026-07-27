import * as React from "react";

import { cn } from "@/lib/utils";

/** The widths `sync-art-assets.mjs` emits for the portrait master. */
const SRCSET = [64, 128, 256, 512]
  .map((w) => `/images/mylo-portrait-${w}.webp ${w}w`)
  .join(", ");

type MyloMarkProps = Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> & {
  /**
   * Roughly how wide the mark renders, so the browser picks a sensible source.
   * Defaults to the small end — pass a larger hint for hero-sized marks.
   */
  sizes?: string;
  /**
   * Accessible name. Mylo is decorative in most placements (he sits beside copy
   * that already says what is happening), so this is empty by default and the
   * image is hidden from assistive tech. Pass a label only where the mark is
   * the sole carrier of meaning.
   */
  alt?: string;
};

/**
 * Mylo — the mushroom scout. Renders the canonical portrait from
 * `web/art/Mylo/MyloHeadshot.png`, resized to WebP at build time (see
 * `web/scripts/sync-art-assets.mjs`), rather than the hand-drawn SVG that used
 * to stand in for him.
 *
 * The portrait is square; size it with `className` on the wrapper (e.g.
 * `className="h-16 w-16"`). `object-contain` keeps him undistorted if a caller
 * passes a non-square box.
 */
export function MyloMark({
  className,
  sizes = "128px",
  alt = "",
  ...props
}: MyloMarkProps) {
  return (
    <span className={cn("inline-block leading-none", className)} {...props}>
      {/* Plain <img>: this is a static, already-optimized asset, so Next's
          optimizer would only add a round trip. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/images/mylo-portrait-256.webp"
        srcSet={SRCSET}
        sizes={sizes}
        alt={alt}
        aria-hidden={alt === "" ? true : undefined}
        width={256}
        height={256}
        decoding="async"
        className="block h-full w-full object-contain"
      />
    </span>
  );
}
