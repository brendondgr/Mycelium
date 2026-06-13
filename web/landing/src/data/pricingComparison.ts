export type ComparisonCell =
  | { kind: "included" }
  | { kind: "text"; value: string; italic?: boolean };

export type ComparisonRow = {
  feature: string;
  description?: string;
  spore: ComparisonCell;
  lab: ComparisonCell;
  canopy: ComparisonCell;
};

export type ComparisonCategory = {
  title: string;
  rows: ComparisonRow[];
};

export const pricingComparison = {
  eyebrow: "Compare plans",
  title: "Everything included, at a glance",
  subtitle: "All paid plans include a 14-day free trial. No credit card required.",
  plans: [
    { id: "spore", name: "Spore", price: "$10 / user / mo" },
    { id: "lab", name: "Mycelium Lab", price: "$12.50 / member / mo" },
    { id: "canopy", name: "Canopy", price: "$20 / member / mo" },
  ],
  categories: [
    {
      title: "Team & access",
      rows: [
        {
          feature: "Users included",
          spore: { kind: "text", value: "1" },
          lab: { kind: "text", value: "3–15" },
          canopy: { kind: "text", value: "15+" },
        },
        {
          feature: "PI / Co-PI seats",
          description: "Named principal investigators on the account",
          spore: { kind: "included" },
          lab: { kind: "text", value: "Up to 5" },
          canopy: { kind: "text", value: "Unlimited" },
        },
        {
          feature: "Admin panel & billing controls",
          spore: { kind: "included" },
          lab: { kind: "text", value: "Basic", italic: true },
          canopy: { kind: "included" },
        },
        {
          feature: "Multi-lab / department coordination",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
      ],
    },
    {
      title: "Research discovery",
      rows: [
        {
          feature: "Daily literature digests",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Research topics monitored",
          spore: { kind: "text", value: "10" },
          lab: { kind: "text", value: "25 per member" },
          canopy: { kind: "text", value: "Unlimited" },
        },
        {
          feature: "Paper relevance scoring",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Custom research topic feeds",
          description: "Tailored source lists and alert rules",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Weekly opportunity report",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
      ],
    },
    {
      title: "Grants & fellowships",
      rows: [
        {
          feature: "Grant alerts",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Fellowship matching",
          description: "Personalized to each researcher's profile and stage",
          spore: { kind: "text", value: "Personal only", italic: true },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Deadline tracking & reminders",
          spore: { kind: "text", value: "Email only", italic: true },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Grant fit explanations",
          description: "Why a grant matches the lab's current goals",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
      ],
    },
    {
      title: "Lab intelligence",
      rows: [
        {
          feature: "Personal lab profile",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Shared lab profile & goals",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Knowledge graph",
          description: "Connected view of papers, people, projects, and opportunities",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Team opportunity dashboard",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Usage & engagement analytics",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
      ],
    },
    {
      title: "Integrations & access",
      rows: [
        {
          feature: "Email digest delivery",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
        {
          feature: "Mylo Bot — Discord & Slack",
          description: "Add-on pricing applies",
          spore: { kind: "included" },
          lab: { kind: "text", value: "+$10 / mo" },
          canopy: { kind: "text", value: "+$25 / mo" },
        },
        {
          feature: "API access",
          description: "For custom workflows and internal tooling",
          spore: { kind: "included" },
          lab: { kind: "included" },
          canopy: { kind: "included" },
        },
      ],
    },
    {
      title: "Support",
      rows: [
        {
          feature: "Support channel",
          spore: { kind: "text", value: "Email" },
          lab: { kind: "text", value: "Email + chat" },
          canopy: { kind: "text", value: "Priority" },
        },
        {
          feature: "Onboarding assistance",
          spore: { kind: "text", value: "Self-serve", italic: true },
          lab: { kind: "text", value: "Guided setup", italic: true },
          canopy: { kind: "included" },
        },
      ],
    },
  ],
  footnote:
    "Mycelium Lab requires a minimum of 3 members and supports up to 15 members and 5 PIs/Co-PIs. · Canopy requires a minimum of 15 members with no upper limit. · All prices are billed monthly. Annual billing discounts available on request.",
} as const satisfies {
  eyebrow: string;
  title: string;
  subtitle: string;
  plans: ReadonlyArray<{ id: string; name: string; price: string }>;
  categories: ReadonlyArray<ComparisonCategory>;
  footnote: string;
};
