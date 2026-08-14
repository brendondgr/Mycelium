import * as React from "react";

import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon?: React.ReactNode;
  /** Small uppercase eyebrow, e.g. "Coming soon". */
  badge?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
};

/**
 * The honest stand-in for a section whose pipeline does not exist yet (Daily
 * Reports, Opportunities, Deadlines, Reports) or a populated section with no data
 * for this account. Calm, on-brand, and clearly labeled — never fabricated data.
 */
export function EmptyState({
  icon,
  badge,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <section
      className={cn(
        "rounded-2xl border border-dashed border-border bg-surface px-8 py-14 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="relative mx-auto mb-4 h-[60px] w-[60px]">
          <Seedling />
          <div className="relative flex h-full w-full items-center justify-center rounded-2xl bg-surface-alt text-brand-secondary">
            {icon}
          </div>
        </div>
      ) : null}
      {badge ? (
        <span className="mb-3.5 inline-block rounded-full border border-dashed border-border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          {badge}
        </span>
      ) : null}
      <h2 className="font-serif text-xl font-semibold text-[var(--text-primary)]">
        {title}
      </h2>
      {description ? (
        <p className="mx-auto mt-2 max-w-[46ch] text-sm leading-relaxed text-[var(--text-secondary)]">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </section>
  );
}

/** The leaf outline shared with the sidebar vine, drawn around its stem base. */
const LEAF_D = "M0 0 C5 -9 18 -8 24 0 C18 8 5 9 0 0 Z";

/**
 * A seedling that unfurls once out of the top of the empty state's icon tile,
 * then holds.
 *
 * One-shot on purpose: a looping animation in an empty state reads as "still
 * loading", and people sit waiting for data that is never coming. Drawn
 * statically in the markup and animated only by classes that exist under
 * `prefers-reduced-motion: no-preference`, so this stays a server component and
 * degrades to a finished sprout rather than a blank space.
 */
function Seedling() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 120 46"
      width={120}
      height={46}
      fill="none"
      className="pointer-events-none absolute bottom-[calc(100%-6px)] left-1/2 -translate-x-1/2"
    >
      <path
        d="M60 46 C60 34 58 27 60 12"
        pathLength={100}
        stroke="var(--primary)"
        strokeWidth={2}
        strokeLinecap="round"
        className="mycelium-unfurl-stem"
        style={{ strokeDasharray: 100, strokeDashoffset: 0 }}
      />
      {[
        { transform: "translate(59 28) rotate(-42)", opacity: 0.85, delay: "0.38s" },
        { transform: "translate(59 32) rotate(214)", opacity: 0.62, delay: "0.51s" },
        { transform: "translate(60 12)", opacity: 1, delay: "0.64s", spore: true },
      ].map((leaf) => (
        <g key={leaf.transform} transform={leaf.transform}>
          <g
            className="mycelium-unfurl-leaf"
            style={{
              transformBox: "fill-box",
              transformOrigin: leaf.spore ? "center" : "0 50%",
              animationDelay: leaf.delay,
            }}
          >
            {leaf.spore ? (
              <circle r={3} fill="var(--accent)" />
            ) : (
              <path
                d={LEAF_D}
                fill="var(--primary)"
                opacity={leaf.opacity}
                transform="scale(0.72)"
              />
            )}
          </g>
        </g>
      ))}
    </svg>
  );
}
