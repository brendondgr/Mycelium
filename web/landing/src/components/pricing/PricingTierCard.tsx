import { ArrowUpRight, Check, Minus } from "lucide-react";

import { TierMark } from "@/components/pricing/TierMark";
import type { PricingTier } from "@/data/pricing";
import { cn } from "@/lib/utils";

type PricingTierCardProps = {
  tier: PricingTier;
};

export function PricingTierCard({ tier }: PricingTierCardProps) {
  return (
    <article
      className={cn(
        // `reveal-fade` rather than `reveal`: the featured tier is already
        // lifted and scaled by its own utilities, and a reveal that also moved
        // it would fight them.
        "tier-card reveal-fade relative flex h-full flex-col rounded-2xl bg-card",
        tier.featured
          ? "tier-card-featured p-7 sm:p-8 lg:p-9 md:-translate-y-2 md:scale-[1.03] motion-reduce:translate-y-0 motion-reduce:scale-100"
          : "border border-border p-6 shadow-[0_10px_30px_rgb(52_39_20/5%)] sm:p-7",
        tier.featured ? "order-first md:order-none" : undefined,
      )}
    >
      {tier.featured ? (
        <span className="absolute left-1/2 top-0 flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 whitespace-nowrap rounded-full border border-[color-mix(in_srgb,var(--brand-accent)_55%,transparent)] bg-card px-3.5 py-1 text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-[var(--text-primary)] shadow-sm">
          <span className="size-1.5 rounded-full bg-[var(--brand-accent)]" aria-hidden="true" />
          Most popular
        </span>
      ) : null}

      <div className="text-center">
        <TierMark
          id={tier.id}
          className={cn(
            "mx-auto size-11",
            tier.featured ? "text-primary" : "text-[var(--brand-secondary)]",
          )}
        />
        <h3 className="mt-4 font-display text-xl font-medium text-[var(--text-primary)]">
          {tier.name}
        </h3>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{tier.audience}</p>
      </div>

      <div className="mt-6 text-center">
        <p className="flex flex-wrap items-baseline justify-center gap-x-2 gap-y-1">
          <span className="font-display text-[2.6rem] font-medium leading-none tracking-tight text-[var(--text-primary)]">
            {tier.price}
          </span>
          <span className="text-sm text-[var(--text-secondary)]">{tier.priceUnit}</span>
        </p>
        <p className="mt-2.5 text-sm text-[var(--text-secondary)]">{tier.billingNote}</p>
      </div>

      <div className="my-6 flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-[var(--divider)]" />
        <span
          className={cn(
            "size-1.5 rotate-45",
            tier.featured ? "bg-[var(--brand-accent)]" : "bg-[var(--divider)]",
          )}
        />
        <span className="h-px flex-1 bg-[var(--divider)]" />
      </div>

      <ul className="flex flex-1 flex-col gap-3" aria-label={`${tier.name} features`}>
        {tier.features.map((feature) => (
          <li key={feature.text} className="flex items-start gap-3 text-sm leading-6">
            {feature.included ? (
              <Check
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-primary"
                strokeWidth={2.5}
              />
            ) : (
              <Minus
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                strokeWidth={2}
              />
            )}
            <span
              className={cn(
                feature.included ? "text-[var(--text-secondary)]" : "text-muted-foreground",
              )}
            >
              {feature.text}
            </span>
            {/* Fit must never rest on the icon's color alone. */}
            <span className="sr-only">{feature.included ? "included" : "not included"}</span>
          </li>
        ))}
      </ul>

      <a
        className={cn(
          "mt-8 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full px-5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          tier.featured
            ? "bg-primary text-primary-foreground hover:bg-brand-primary-hover"
            : "border border-border text-[var(--text-primary)] hover:bg-secondary",
        )}
        href={tier.ctaHref}
      >
        Start free
        <ArrowUpRight aria-hidden className="size-4" />
      </a>
    </article>
  );
}
