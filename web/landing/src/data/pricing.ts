import type { LucideIcon } from "lucide-react";
import { Building2, FlaskConical, Sprout } from "lucide-react";

import { appLoginUrl } from "@/data/site";

export type PricingFeature = {
  text: string;
  included: boolean;
};

export type PricingTier = {
  id: string;
  name: string;
  audience: string;
  price: string;
  priceUnit: string;
  billingNote: string;
  icon: LucideIcon;
  featured?: boolean;
  features: PricingFeature[];
  ctaHref: string;
};

export type PricingAddon = {
  id: string;
  name: string;
  description: string;
  price: string;
  availability: string;
  variant: "discord" | "slack";
};

export const pricingHero = {
  title: "Research intelligence for every scale",
  description:
    "From solo researchers to entire departments — Mylo finds what matters, so your team can focus on the work.",
} as const;

export const pricingTiers = [
  {
    id: "spore",
    name: "Spore",
    audience: "For solo researchers and independent grad students.",
    price: "$10",
    priceUnit: "per month",
    billingNote: "1 user · billed monthly",
    icon: Sprout,
    features: [
      { text: "Daily literature digests", included: true },
      { text: "Up to 10 research topics", included: true },
      { text: "Semantic literature search", included: true },
      { text: "Weekly pulse summaries", included: true },
      { text: "Team features", included: false },
      { text: "Discord / Slack bot", included: false },
    ],
    ctaHref: appLoginUrl,
  },
  {
    id: "mycelium-lab",
    name: "Mycelium Lab",
    audience: "For research labs with an active PI and team.",
    price: "$12.50",
    priceUnit: "per member / month",
    billingNote: "Min 3 · max 15 members · up to 5 PIs",
    icon: FlaskConical,
    featured: true,
    features: [
      { text: "Everything in Spore", included: true },
      { text: "Team workspace", included: true },
      { text: "Member profiles", included: true },
      { text: "Shared evidence graph", included: true },
      { text: "Grant alerts", included: true },
      { text: "Discord / Slack bot eligible", included: true },
    ],
    ctaHref: appLoginUrl,
  },
  {
    id: "canopy",
    name: "Canopy",
    audience: "For large labs, departments, or research institutes.",
    price: "$20",
    priceUnit: "per member / month",
    billingNote: "Min 15 members · unlimited PIs",
    icon: Building2,
    features: [
      { text: "Everything in Mycelium Lab", included: true },
      { text: "Unlimited PIs", included: true },
      { text: "Department-wide routing", included: true },
      { text: "Priority support", included: true },
      { text: "Advanced admin controls", included: true },
      { text: "Department bot eligible", included: true },
    ],
    ctaHref: appLoginUrl,
  },
] as const satisfies ReadonlyArray<PricingTier>;

export const pricingAddons = [
  {
    id: "lab-bot",
    name: "Lab bot",
    description:
      "Surface digests, grant alerts, and evidence updates in your lab Discord channel.",
    price: "+$10 / month",
    availability: "Available on Mycelium Lab",
    variant: "discord",
  },
  {
    id: "department-bot",
    name: "Department bot",
    description:
      "Route alerts and digests across multiple channels with role-aware delivery.",
    price: "+$25 / month",
    availability: "Available on Canopy",
    variant: "slack",
  },
] as const satisfies ReadonlyArray<PricingAddon>;

export const pricingFooter = {
  trial:
    "All plans include a 14-day free trial. No credit card required to start.",
  customPrompt: "Need something custom?",
  customLinkLabel: "Talk to us",
  customHref: "/contact",
} as const;
