import { ArrowUpRight } from "lucide-react";

import { PricingAddons } from "@/components/pricing/PricingAddons";
import { PricingTierCard } from "@/components/pricing/PricingTierCard";
import { pricingFooter, pricingHero, pricingTiers } from "@/data/pricing";

export function PricingSection() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
      <header className="mx-auto max-w-2xl text-center">
        <h1 className="font-display text-3xl font-semibold leading-tight text-[var(--text-primary)] sm:text-4xl lg:text-[2.75rem] lg:leading-[1.1]">
          {pricingHero.title}
        </h1>
        <p className="mt-4 text-base leading-7 text-[var(--text-secondary)] sm:text-lg sm:leading-8">
          {pricingHero.description}
        </p>
      </header>

      <section className="mt-14 sm:mt-16" aria-labelledby="pricing-tiers-heading">
        <h2 id="pricing-tiers-heading" className="sr-only">
          Pricing plans
        </h2>
        <div className="grid items-center gap-6 lg:grid-cols-3 lg:gap-5 xl:gap-6">
          {pricingTiers.map((tier) => (
            <PricingTierCard key={tier.id} tier={tier} />
          ))}
        </div>
      </section>

      <PricingAddons />

      <footer className="mt-16 border-t border-border pt-10 text-center sm:mt-20 sm:pt-12">
        <p className="text-sm leading-6 text-[var(--text-secondary)] sm:text-base">
          {pricingFooter.trial}
        </p>
        <p className="mt-4 text-sm text-muted-foreground sm:text-base">
          {pricingFooter.customPrompt}{" "}
          <a
            className="inline-flex items-center gap-1 font-medium text-primary underline-offset-2 transition hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            href={pricingFooter.customHref}
          >
            {pricingFooter.customLinkLabel}
            <ArrowUpRight aria-hidden className="size-4" />
          </a>
        </p>
      </footer>
    </div>
  );
}
