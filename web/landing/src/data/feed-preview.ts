/**
 * Illustrative feed content for the public site.
 *
 * Fictional by design — the real feeds are lab-scoped and permission-gated, so
 * nothing real can appear here. What is *not* fictional is the shape: every
 * field below stands for one the app's feed cards draw, and the cards render
 * nothing that is absent here. When the card skeleton in
 * `web/app/src/components/portal/feed/parts.tsx` or a feed's config in
 * `web/app/src/components/portal/sections/` changes, this file and the cards in
 * `components/landing/feed/` are what have to follow.
 *
 * Rules the preview inherits from the app (`docs/styles.md`, "How a
 * recommendation states itself"):
 *
 * 1. **The match is measured.** `embeddingMatch` stands for the API's
 *    `embedding_match` — the embedding similarity between the item and the
 *    reader's profile — and each theme's `score` for its `per_cluster` fusion
 *    score. The card derives every figure from these two exactly as the app
 *    does (`feed/match.ts`); no figure here is typed in as a theme percentage.
 * 2. **No position and no verdict.** Those belong to the report, not the feed.
 * 3. **The caveat is not on the card.** It lives in the opened item, under "Why
 *    it might not", and the preview has no opened item.
 * 4. **Both reason origins appear.** `"llm"` is Mylo (his portrait rides the
 *    line); `"fallback"` is the deterministic topical match many readers are
 *    actually on. Showing only Mylo's would overstate how often he writes one.
 */

/** A theme the item reached: its name, palette token (1–8), and pull. */
export type FeedTheme = {
  label: string;
  /** `--cluster-N`. The app hashes a theme's id to pick one; these are fixed. */
  token: string;
  /** The theme's fusion score (`per_cluster`) — not a percentage; runs past 1. */
  score: number;
};

type FeedItemCore = {
  title: string;
  /** Mylo's reason, shown on one line. */
  reason: string;
  origin: "llm" | "fallback";
  /** Embedding similarity to the reader's profile, 0–100 (`embedding_match`). */
  embeddingMatch: number;
  /** The attributed theme first, then the others whose slate it reached. */
  themes: readonly FeedTheme[];
  /** Entered this reader's slate on the last run. Never "published today". */
  isNew?: boolean;
};

export type PaperItem = FeedItemCore & {
  kind: "paper";
  /** The venue's short name on the card; the full masthead on hover. */
  venue: string;
  venueFull: string;
  /** "Okonkwo et al." */
  authors: string;
  year: number;
};

/*
 * Dates are offsets in days from the day the site is built (see `feed/match.ts`),
 * so a fictional deadline never reads as closed on a page that shipped months ago.
 */

export type GrantItem = FeedItemCore & {
  kind: "grant";
  sponsor: string;
  amount: string;
  deadlineInDays: number;
  postedDaysAgo: number;
  /** The listing changed since Mylo last read it. */
  isUpdated?: boolean;
};

export type FellowshipItem = FeedItemCore & {
  kind: "fellowship";
  awardClass: string;
  amount: string;
  /** `null` for a rolling call. */
  deadlineInDays: number | null;
  /** Academic stages; the card shows three at most. */
  stages: readonly string[];
  /** The rule engine's tier. An award that fails the gate never reaches a
   * card, so there is no "Not eligible" value to render. */
  eligibility: "Qualified" | "Possible fit" | "Eligibility not listed";
};

export type ConferenceItem = FeedItemCore & {
  kind: "conference";
  acronym: string;
  place: string;
  deadlineInDays: number;
  /** When the event opens, and how many days it runs. */
  eventInDays: number;
  eventLength: number;
  isUpdated?: boolean;
  /** Informational only — a flag never hides or reorders a venue. */
  qualityFlags?: readonly string[];
  /** Mylo's note that a deadline's *kind* may be mislabelled at the source. */
  dateWarning?: string;
};

export type FeedItem = PaperItem | GrantItem | FellowshipItem | ConferenceItem;

export type FeedTab = {
  id: "papers" | "grants" | "fellowships" | "conferences";
  label: string;
  items: readonly FeedItem[];
};

/* The fictional lab's four themes. */
const RETRIEVAL = { label: "Retrieval grounding", token: "1" };
const PLASTICITY = { label: "Plasticity mechanisms", token: "2" };
const CLINICAL = { label: "Clinical CDS safety", token: "3" };
const DECODING = { label: "Neural decoding", token: "4" };

export const feedTabs: readonly FeedTab[] = [
  {
    id: "papers",
    label: "Papers",
    items: [
      {
        kind: "paper",
        title: "Retrieval-grounded clinical decision support under distribution shift",
        venue: "Nat. Mach. Intell.",
        venueFull: "Nature Machine Intelligence",
        authors: "Okonkwo et al.",
        year: 2026,
        reason:
          "It measures the exact failure you flagged after the Lakeside rollout — grounding falling off as the deployment population drifts — and its harness runs on MIMIC-IV, which you already have.",
        origin: "llm",
        isNew: true,
        embeddingMatch: 84,
        themes: [
          { ...RETRIEVAL, score: 1.32 },
          { ...CLINICAL, score: 0.94 },
          { ...DECODING, score: 0.31 },
        ],
      },
      {
        kind: "paper",
        title: "Limits of multi-hop verification in clinical question answering",
        venue: "JAMIA",
        venueFull: "Journal of the American Medical Informatics Association",
        authors: "Reyes et al.",
        year: 2025,
        reason: "Matches your Retrieval grounding work through its overlap with clinical question answering.",
        origin: "fallback",
        embeddingMatch: 68,
        themes: [
          { ...RETRIEVAL, score: 1.05 },
          { ...CLINICAL, score: 0.97 },
        ],
      },
    ],
  },
  {
    id: "grants",
    label: "Grants",
    items: [
      {
        kind: "grant",
        title: "Smart Health and Biomedical Research in the Era of AI",
        sponsor: "National Science Foundation",
        amount: "$1.2M / 4 yrs",
        deadlineInDays: 46,
        postedDaysAgo: 19,
        reason:
          "The interdisciplinary requirement is already met by the lab's clinical arm, and the budget sits between your last two awards rather than above them.",
        origin: "llm",
        isNew: true,
        embeddingMatch: 79,
        themes: [
          { ...CLINICAL, score: 1.18 },
          { ...RETRIEVAL, score: 0.71 },
        ],
      },
      {
        kind: "grant",
        title: "R21 Exploratory/Developmental Research Award",
        sponsor: "National Institutes of Health",
        amount: "$275K / 2 yrs",
        deadlineInDays: 11,
        postedDaysAgo: 64,
        reason:
          "Matches your Plasticity mechanisms work through its overlap with exploratory neuroscience methods.",
        origin: "fallback",
        isUpdated: true,
        embeddingMatch: 62,
        themes: [
          { ...PLASTICITY, score: 0.9 },
          { ...DECODING, score: 0.52 },
        ],
      },
    ],
  },
  {
    id: "fellowships",
    label: "Fellowships",
    items: [
      {
        kind: "fellowship",
        title: "NSF Graduate Research Fellowship Program",
        awardClass: "Predoctoral",
        amount: "$37K / yr",
        deadlineInDays: 33,
        stages: ["First-year graduate", "Undergraduate senior"],
        eligibility: "Qualified",
        reason:
          "It is judged on the applicant rather than a project, which suits two members whose strongest material is their own methods work.",
        origin: "llm",
        isNew: true,
        embeddingMatch: 74,
        themes: [
          { ...PLASTICITY, score: 1.0 },
          { ...DECODING, score: 0.55 },
        ],
      },
      {
        kind: "fellowship",
        title: "Ford Foundation Predoctoral Fellowship",
        awardClass: "Predoctoral",
        amount: "$27K / yr",
        deadlineInDays: null,
        stages: ["Doctoral"],
        eligibility: "Possible fit",
        reason: "Field and stage both clear, but the award is not tied to any one strand of your work.",
        origin: "fallback",
        embeddingMatch: 48,
        themes: [{ ...RETRIEVAL, score: 0.6 }],
      },
    ],
  },
  {
    id: "conferences",
    label: "Conferences",
    items: [
      {
        kind: "conference",
        title: "NeurIPS — Datasets & Benchmarks Track",
        acronym: "NeurIPS D&B",
        place: "San Diego, USA",
        deadlineInDays: 27,
        eventInDays: 131,
        eventLength: 7,
        reason:
          "The track reviews on documentation and reusability, where your evaluation harness is strongest, and the abstract lands three weeks before your defence.",
        origin: "llm",
        isNew: true,
        embeddingMatch: 81,
        themes: [
          { ...RETRIEVAL, score: 1.21 },
          { ...PLASTICITY, score: 0.62 },
          { ...CLINICAL, score: 0.48 },
          { ...DECODING, score: 0.3 },
        ],
      },
      {
        kind: "conference",
        title: "AMIA Annual Symposium",
        acronym: "AMIA",
        place: "Washington DC, USA",
        deadlineInDays: 58,
        eventInDays: 152,
        eventLength: 5,
        reason: "Matches your Clinical CDS safety work through its overlap with clinical informatics venues.",
        origin: "fallback",
        isUpdated: true,
        qualityFlags: ["Repeated extensions", "Fees prominent"],
        dateWarning: "The source lists this as a paper deadline, but the call describes it as an abstract round.",
        embeddingMatch: 77,
        themes: [
          { ...CLINICAL, score: 1.1 },
          { ...RETRIEVAL, score: 0.83 },
        ],
      },
    ],
  },
];
