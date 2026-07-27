import { ArrowUpRight } from "lucide-react";

import { PricingAddons } from "@/components/pricing/PricingAddons";
import { PricingComparison } from "@/components/pricing/PricingComparison";
import { PricingTierCard } from "@/components/pricing/PricingTierCard";
import { pricingFooter, pricingHero, pricingTiers } from "@/data/pricing";

export function PricingSection() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
      <header className="mx-auto max-w-2xl text-center">
        <p className="text-sm font-medium uppercase tracking-[0.14em] eyebrow">Pricing</p>
        <h1 className="font-display mt-3 text-[clamp(2.1rem,5.4vw,3.25rem)] font-medium leading-[1.06] text-[var(--text-primary)]">
          {pricingHero.title}
        </h1>

        <div className="mx-auto mt-6 flex w-full max-w-[13rem] items-center gap-3" aria-hidden="true">
          <span className="h-px flex-1 bg-[var(--divider)]" />
          <span className="size-1.5 rotate-45 bg-[var(--brand-accent)]" />
          <span className="h-px flex-1 bg-[var(--divider)]" />
        </div>

        <p className="mt-6 text-base leading-7 text-[var(--text-secondary)] sm:text-lg sm:leading-8">
          {pricingHero.description}
        </p>
      </header>

      <section className="mt-16 sm:mt-20" aria-labelledby="pricing-tiers-heading">
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

      <PricingComparison />

      <footer className="mt-12 border-t border-border pt-10 text-center sm:mt-14 sm:pt-12">
        <p className="text-sm leading-6 text-[var(--text-secondary)] sm:text-base">
          {pricingFooter.trial}
        </p>
        <p className="mt-4 text-sm text-[var(--text-secondary)] sm:text-base">
          {pricingFooter.customPrompt}{" "}
          <a
            className="inline-flex items-center gap-1 font-medium text-[var(--brand-primary-hover)] underline-offset-2 transition hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
