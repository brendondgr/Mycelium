import { ArrowUpRight, Check, Minus } from "lucide-react";

import type { PricingTier } from "@/data/pricing";
import { cn } from "@/lib/utils";

type PricingTierCardProps = {
  tier: PricingTier;
};

export function PricingTierCard({ tier }: PricingTierCardProps) {
  const Icon = tier.icon;

  return (
    <article
      className={cn(
        "relative flex h-full flex-col rounded-xl border bg-card shadow-sm",
        tier.featured
          ? "border-2 border-primary p-7 shadow-[0_16px_48px_rgb(94_122_62/14%)] sm:p-8 lg:p-9 md:-translate-y-2 md:scale-[1.04] motion-reduce:translate-y-0 motion-reduce:scale-100"
          : "border-border p-6 sm:p-7",
        tier.featured ? "order-first md:order-none" : undefined,
      )}
    >
      {tier.featured ? (
        <span className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
          Most popular
        </span>
      ) : null}

      <div className="text-center">
        <span
          className="mx-auto inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary"
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        <h3 className="mt-4 text-sm font-semibold uppercase tracking-[0.14em] text-primary">
          {tier.name}
        </h3>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{tier.audience}</p>
      </div>

      <div className="mt-6 text-center">
        <p className="flex flex-wrap items-baseline justify-center gap-x-2 gap-y-1">
          <span className="text-4xl font-semibold tracking-tight text-[var(--text-primary)]">
            {tier.price}
          </span>
          <span className="text-sm text-[var(--text-secondary)]">{tier.priceUnit}</span>
        </p>
        <p className="mt-2 text-sm italic text-muted-foreground">{tier.billingNote}</p>
      </div>

      <ul className="mt-6 flex flex-1 flex-col gap-3" aria-label={`${tier.name} features`}>
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
          </li>
        ))}
      </ul>

      <a
        className="mt-8 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-border px-5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        href={tier.ctaHref}
      >
        Get started
        <ArrowUpRight aria-hidden className="size-4" />
      </a>
    </article>
  );
}
