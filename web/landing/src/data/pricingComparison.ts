export type ComparisonCell =
  | { kind: "check" }
  | { kind: "cross" }
  | { kind: "partial"; value: string }
  | { kind: "text"; value: string };

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
    {
      id: "spore",
      name: "Spore",
      price: "$10",
      priceUnit: "/ user / mo",
      pillClass: "bg-[#eaf3de] text-[#3b6d11]",
    },
    {
      id: "lab",
      name: "Mycelium Lab",
      price: "$12.50",
      priceUnit: "/ member / mo",
      pillClass: "bg-[#e1f5ee] text-[#0f6e56]",
      highlighted: true,
    },
    {
      id: "canopy",
      name: "Canopy",
      price: "$20",
      priceUnit: "/ member / mo",
      pillClass: "bg-[#e6f1fb] text-[#185fa5]",
    },
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
          spore: { kind: "cross" },
          lab: { kind: "text", value: "Up to 5" },
          canopy: { kind: "text", value: "Unlimited" },
        },
        {
          feature: "Admin panel & billing controls",
          spore: { kind: "cross" },
          lab: { kind: "partial", value: "Basic" },
          canopy: { kind: "check" },
        },
        {
          feature: "Multi-lab / department coordination",
          spore: { kind: "cross" },
          lab: { kind: "cross" },
          canopy: { kind: "check" },
        },
      ],
    },
    {
      title: "Research discovery",
      rows: [
        {
          feature: "Daily literature digests",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Research topics monitored",
          spore: { kind: "text", value: "10" },
          lab: { kind: "text", value: "25 per member" },
          canopy: { kind: "text", value: "Unlimited" },
        },
        {
          feature: "Paper relevance scoring",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Custom research topic feeds",
          description: "Tailored source lists and alert rules",
          spore: { kind: "cross" },
          lab: { kind: "cross" },
          canopy: { kind: "check" },
        },
        {
          feature: "Weekly opportunity report",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
      ],
    },
    {
      title: "Grants & fellowships",
      rows: [
        {
          feature: "Grant alerts",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Fellowship matching",
          description: "Personalized to each researcher's profile and stage",
          spore: { kind: "partial", value: "Personal only" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Deadline tracking & reminders",
          spore: { kind: "partial", value: "Email only" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Grant fit explanations",
          description: "Why a grant matches the lab's current goals",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
      ],
    },
    {
      title: "Lab intelligence",
      rows: [
        {
          feature: "Personal lab profile",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Shared lab profile & goals",
          spore: { kind: "cross" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Knowledge graph",
          description: "Connected view of papers, people, projects, and opportunities",
          spore: { kind: "cross" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Team opportunity dashboard",
          spore: { kind: "cross" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Usage & engagement analytics",
          spore: { kind: "cross" },
          lab: { kind: "cross" },
          canopy: { kind: "check" },
        },
      ],
    },
    {
      title: "Integrations & access",
      rows: [
        {
          feature: "Email digest delivery",
          spore: { kind: "check" },
          lab: { kind: "check" },
          canopy: { kind: "check" },
        },
        {
          feature: "Mylo Bot — Discord & Slack",
          description: "Add-on pricing applies",
          spore: { kind: "cross" },
          lab: { kind: "partial", value: "+$10 / mo" },
          canopy: { kind: "partial", value: "+$25 / mo" },
        },
        {
          feature: "API access",
          description: "For custom workflows and internal tooling",
          spore: { kind: "cross" },
          lab: { kind: "cross" },
          canopy: { kind: "check" },
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
          spore: { kind: "partial", value: "Self-serve" },
          lab: { kind: "partial", value: "Guided setup" },
          canopy: { kind: "check" },
        },
      ],
    },
  ],
} as const satisfies {
  eyebrow: string;
  title: string;
  subtitle: string;
  plans: ReadonlyArray<{
    id: string;
    name: string;
    price: string;
    priceUnit: string;
    pillClass: string;
    highlighted?: boolean;
  }>;
  categories: ReadonlyArray<ComparisonCategory>;
};
