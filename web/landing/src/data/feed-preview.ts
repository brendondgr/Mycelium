/**
 * Illustrative feed content for the public site.
 *
 * Fictional by design — the real feeds are lab-scoped and permission-gated, so
 * nothing real can appear here. What is *not* fictional is the shape: every
 * field below exists on the live cards, and the cards render nothing that is
 * absent here. When a feed section in `web/app/src/components/portal/sections/`
 * gains or loses a field, this file and the four card components in
 * `components/landing/` are what have to follow.
 *
 * Two rules the preview inherits from the app and must not quietly break:
 *
 * 1. **No judgement element.** No percent, no per-theme position, no Read /
 *    Skim / File chip. The backend computes and serves all of them; the app's
 *    feed cards deliberately draw none. See `docs/styles.md`, "How a
 *    recommendation states itself".
 * 2. **The caveat is mandatory.** `apps/content/cluster_fit.py` refuses an
 *    empty one, so no item here may omit it either. It is the element that
 *    distinguishes Mylo from a recommender: he says what would make an item a
 *    waste of your time.
 */

/** One dated round, as `DeadlineMenu` lists it. */
export type FeedDeadline = {
  /** "Application", "Round 2", "Abstract", "Full paper". */
  label: string;
  date: string;
  /** Struck through in the menu — this round has closed. */
  passed?: boolean;
  /** Rendered with an "(est.)" suffix — projected from last cycle. */
  anticipated?: boolean;
};

type FeedItemCore = {
  title: string;
  /** The listing's own blurb — the card's `description`. */
  description?: string;
  /**
   * The one-sentence "why this matched". Rendered in Mylo's soft green field
   * when `origin` is `"llm"`, and as a plain paragraph otherwise.
   */
  reason: string;
  /**
   * The strongest reason this might *not* be worth the reader's time. Never
   * optional, never empty — the model's parser rejects an empty one and falls
   * back to the deterministic template.
   */
  caveat: string;
  /** One clause on what two themes share here. Only when the item bridges. */
  bridgeNote?: string;
  /**
   * Who wrote the reason. `"llm"` is Mylo; `"fallback"` is the deterministic
   * topical match most readers are actually on. The preview must show both, or
   * it overstates how often the green box appears.
   */
  origin: "llm" | "fallback";
  /** The theme this item was matched under, and its palette token (1–8). */
  cluster: string;
  clusterToken: string;
  /** The other theme whose slate this item also reached — the "Also:" badge. */
  bridge?: string;
  /** Entered this reader's slate on the last run. Never "published today". */
  isNew?: boolean;
  /** Grants and conferences only: the listing itself changed. */
  isUpdated?: boolean;
};

export type PaperItem = FeedItemCore & {
  kind: "paper";
  /** First meta line: "source · venue". */
  provenance: string;
  /** Second meta line: "year · first author et al.". */
  byline: string;
  /** Sits below the cross-topics divider, carrying the neutral pill. */
  crossTopics?: boolean;
};

/** Grants, fellowships and conferences share the action bar and the source row. */
type OpportunityCore = FeedItemCore & {
  deadlines: readonly FeedDeadline[];
  /** The licence / provenance line at the foot of the card. */
  sourceCredit: string;
};

export type GrantItem = OpportunityCore & {
  kind: "grant";
  /** Joined into the identity line as "<sponsor>; Original Posted <posted>". */
  sponsor: string;
  posted: string;
  amount: string;
  /** The note under the divider in the deadline popover. */
  deadlineFootnote?: string;
};

export type FellowshipItem = OpportunityCore & {
  kind: "fellowship";
  amount: string;
  /** The award class stands in for a sponsor on the identity line. */
  awardClass: string;
  posted: string;
  /** Which band heading this sits under. */
  band: "matched" | "open";
  /** The rule engine's tier. An award that fails the gate never reaches a card,
   * so there is no "Not eligible" value to render. */
  eligibility?: "Qualified" | "Possible fit" | "Eligibility not listed";
  eligibilityBullets?: readonly string[];
  /** Research fields and academic stages, capped at four on the card. */
  facets?: readonly string[];
};

export type ConferenceItem = OpportunityCore & {
  kind: "conference";
  /** Joined into the identity line as "<location>; <eventDates>". */
  location: string;
  eventDates: string;
  rankings?: readonly { system: string; rank: string }[];
  /** Informational only — a flag never hides or reorders a venue. */
  qualityFlags?: readonly string[];
  openWindows?: readonly string[];
  /** Mylo's note that a deadline's *kind* may be mislabelled at the source. */
  dateWarning?: string;
};

export type FeedItem = PaperItem | GrantItem | FellowshipItem | ConferenceItem;

export type FeedTab = {
  id: "papers" | "grants" | "fellowships" | "conferences";
  label: string;
  /** Eyebrow + title, as `SectionHeader` renders them. */
  eyebrow: string;
  title: string;
  /** The subtitle, in the shape the section actually writes it. */
  blurb: string;
  /** The search field's placeholder, verbatim from the feed. */
  searchPlaceholder: string;
  /** The rail's filter groups. Papers have no rail. */
  filters?: readonly { label: string; options: readonly string[] }[];
  items: readonly FeedItem[];
};

/**
 * The deterministic caveat, verbatim from `cluster_fit.py`. This is what a
 * reader without model reasoning sees, and it is honest rather than broken —
 * so the preview shows it rather than pretending every row is model-written.
 */
const TOPICAL_CAVEAT =
  "Mylo has not read this one for you — the placement is a topical match, not a judgement of the work itself.";

export const feedTabs: readonly FeedTab[] = [
  {
    id: "papers",
    label: "Papers",
    eyebrow: "Your feed",
    title: "Research Papers",
    blurb:
      "48 papers matched your research — top 10 ranked by Mylo · gathered this morning.",
    searchPlaceholder: "Search papers by title or abstract…",
    items: [
      {
        kind: "paper",
        title: "Retrieval-grounded clinical decision support under distribution shift",
        provenance: "OpenAlex · Nature Machine Intelligence",
        byline: "2026 · Okonkwo et al.",
        description:
          "Evaluates retrieval-augmented decision support across four hospital systems, and reports where grounding degrades once the deployment population drifts away from the index corpus.",
        reason:
          "It measures the exact failure you flagged after the Lakeside rollout — grounding quality falling off as the deployment population drifts — and the released evaluation harness runs on MIMIC-IV, which you already have.",
        caveat:
          "Every site in the study is an academic medical centre, so it says nothing about the community-hospital deployment your grant is actually scoped to.",
        origin: "llm",
        isNew: true,
        cluster: "Retrieval grounding",
        clusterToken: "1",
      },
      {
        kind: "paper",
        title: "Contrastive pretraining for sparse neural recordings",
        provenance: "bioRxiv · preprint",
        byline: "2026 · Halvorsen et al.",
        description:
          "A contrastive objective for high-density probe data that holds up when only a few hundred labelled trials are available per animal.",
        reason:
          "The low-label regime it targets is the one your plasticity work sits in, and the readout argument in the Q3 proposal would be stronger citing a method that survives a few hundred trials per animal.",
        caveat:
          "It is a preprint with no released code, so adopting the objective means reimplementing it from the paper's description.",
        origin: "llm",
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
      },
      {
        kind: "paper",
        title: "Limits of multi-hop verification in clinical question answering",
        provenance: "PubMed · JAMIA",
        byline: "2025 · Reyes et al.",
        description:
          "Characterises where chained retrieval breaks down on clinical questions that require reconciling two sources, and proposes an abstention criterion.",
        reason:
          "Matches your Retrieval grounding work through its overlap with clinical question answering.",
        caveat: TOPICAL_CAVEAT,
        bridgeNote: "Also in your Clinical CDS safety slate.",
        origin: "fallback",
        crossTopics: true,
        cluster: "Retrieval grounding",
        clusterToken: "1",
        bridge: "Clinical CDS safety",
      },
    ],
  },
  {
    id: "grants",
    label: "Grants",
    eyebrow: "Opportunities",
    title: "Grants",
    blurb: "12 grants matched your research profile and timeline.",
    searchPlaceholder: "Search grants by title, sponsor, or description…",
    filters: [
      { label: "Sort by", options: ["Best match", "Deadline", "Newest"] },
      { label: "Deadline", options: ["Any", "30 days", "90 days"] },
      { label: "Match source", options: ["All", "Mylo", "Similarity"] },
    ],
    items: [
      {
        kind: "grant",
        title: "Smart Health and Biomedical Research in the Era of AI",
        description:
          "Full proposals for interdisciplinary work joining computing research with a named clinical partner. No preliminary award history required.",
        reason:
          "The interdisciplinary requirement is already satisfied by the clinical arm of the lab, and the budget band sits between your last two awards rather than above them.",
        caveat:
          "It requires a named clinical partner committed at submission, and the Lakeside agreement is still unsigned.",
        origin: "llm",
        isNew: true,
        cluster: "Clinical CDS safety",
        clusterToken: "3",
        sponsor: "National Science Foundation",
        posted: "Mar 4",
        amount: "$1.2M / 4 yrs",
        deadlines: [
          { label: "Letter of intent", date: "Jun 2", passed: true },
          { label: "Full proposal", date: "Sep 1" },
          { label: "Round 2", date: "Feb 14", anticipated: true },
        ],
        deadlineFootnote:
          "Letter of intent was required and has closed. Round 2 is projected from last cycle, not announced.",
        sourceCredit: "Grants.gov · public domain",
      },
      {
        kind: "grant",
        title: "R21 Exploratory/Developmental Research Award",
        description:
          "Two years of support for high-risk, high-reward exploratory work. Preliminary data is explicitly not required, and is not scored.",
        reason:
          "Matches your Plasticity mechanisms work through its overlap with exploratory neuroscience methods.",
        caveat: TOPICAL_CAVEAT,
        origin: "fallback",
        isUpdated: true,
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
        sponsor: "National Institutes of Health",
        posted: "Feb 16",
        amount: "$275K / 2 yrs",
        deadlines: [
          { label: "Application", date: "Oct 16" },
          { label: "Application", date: "Feb 16", anticipated: true },
        ],
        deadlineFootnote: "First posted deadline was Oct 5, moved by the sponsor.",
        sourceCredit: "NIH RePORTER · public domain",
      },
    ],
  },
  {
    id: "fellowships",
    label: "Fellowships",
    eyebrow: "Opportunities",
    title: "Fellowships",
    blurb:
      "7 fellowships matched to your research, career stage, and timeline.",
    searchPlaceholder: "Search fellowships by title, field, or description…",
    filters: [
      { label: "Sort by", options: ["Best match", "Deadline"] },
      { label: "Eligibility", options: ["All", "Qualified"] },
      { label: "Academic stage", options: ["Predoctoral", "Postdoctoral"] },
    ],
    items: [
      {
        kind: "fellowship",
        title: "NSF Graduate Research Fellowship Program",
        description:
          "Three years of support across a five-year window for graduate students in NSF-supported fields, awarded on the strength of the applicant rather than a project.",
        reason:
          "The award is judged on the applicant rather than a project, which suits two members whose strongest material is their own methods work rather than a funded aim.",
        caveat:
          "Only students who have completed at most one academic year of graduate study are eligible, which rules out everyone in the lab past their first year.",
        origin: "llm",
        isNew: true,
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
        band: "matched",
        awardClass: "Predoctoral",
        posted: "Jul 30",
        eligibility: "Qualified",
        eligibilityBullets: [
          "US citizen, national, or permanent resident",
          "Enrolled in, or applying to, a research-based master's or doctoral programme",
          "At most one completed academic year of graduate study",
        ],
        facets: ["Neuroscience", "Computer science", "Predoctoral"],
        amount: "$37K / yr",
        deadlines: [
          { label: "Application", date: "Oct 20" },
          { label: "Reference letters", date: "Oct 24" },
        ],
        sourceCredit: "NSF · public domain",
      },
      {
        kind: "fellowship",
        title: "Ford Foundation Predoctoral Fellowship",
        description:
          "Three years of support for doctoral students committed to using diversity as a resource for enriching the education of all students.",
        reason:
          "Field and stage both clear, but the award is not tied to any one strand of your work.",
        caveat: TOPICAL_CAVEAT,
        origin: "fallback",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        band: "open",
        awardClass: "Predoctoral",
        posted: "Jun 11",
        eligibility: "Possible fit",
        eligibilityBullets: [
          "Institutional nomination is required and not yet confirmed",
          "Applicants must have at least three years of study remaining",
        ],
        facets: ["Open to all fields", "Predoctoral"],
        amount: "$27K / yr",
        deadlines: [{ label: "Application", date: "Dec 12" }],
        sourceCredit: "National Academies · terms apply",
      },
    ],
  },
  {
    id: "conferences",
    label: "Conferences",
    eyebrow: "Opportunities",
    title: "Conferences",
    blurb: "9 conferences, ranked by fit · gathered this morning.",
    searchPlaceholder: "Search conferences by title, location, or subject…",
    filters: [
      { label: "Sort by", options: ["Best match", "Deadline"] },
      { label: "Submissions", options: ["Abstract open", "Full paper open"] },
      { label: "Ranking", options: ["Has a rank badge"] },
    ],
    items: [
      {
        kind: "conference",
        title: "NeurIPS — Datasets & Benchmarks Track",
        description:
          "A peer-reviewed track for datasets, benchmarks, and evaluation methodology, reviewed on documentation and reusability as much as on results.",
        reason:
          "The track reviews on documentation and reusability, which is where your evaluation harness is strongest, and the abstract deadline lands three weeks before your defence.",
        caveat:
          "Submissions are camera-ready at review time, so there is no revision round if the reviewers want the deeper-water transects included.",
        origin: "llm",
        isNew: true,
        cluster: "Retrieval grounding",
        clusterToken: "1",
        location: "San Diego, USA",
        eventDates: "Dec 6 – Dec 12, 2026",
        rankings: [
          { system: "CORE", rank: "A*" },
          { system: "CCF", rank: "A" },
        ],
        openWindows: ["Abstract open", "Full paper open"],
        deadlines: [
          { label: "Abstract", date: "May 11" },
          { label: "Full paper", date: "May 15" },
        ],
        sourceCredit: "dblp · ODC-BY",
      },
      {
        kind: "conference",
        title: "AMIA Annual Symposium",
        description:
          "The clinical informatics meeting, with separate tracks for systems papers, evaluation studies, and implementation reports.",
        reason:
          "Matches your Clinical CDS safety work through its overlap with clinical informatics venues.",
        caveat: TOPICAL_CAVEAT,
        origin: "fallback",
        isUpdated: true,
        cluster: "Clinical CDS safety",
        clusterToken: "3",
        location: "Washington DC, USA",
        eventDates: "Nov 14 – Nov 18, 2026",
        rankings: [{ system: "CORE", rank: "A" }],
        qualityFlags: ["Repeated extensions", "Fees prominent"],
        dateWarning:
          "The source lists this as a paper deadline, but the call describes it as an abstract round.",
        openWindows: ["Full paper open"],
        deadlines: [
          { label: "Full paper", date: "Mar 11" },
          { label: "Late-breaking", date: "Jul 9" },
          { label: "Workshop proposals", date: "Jan 20", passed: true },
        ],
        sourceCredit: "dblp · ODC-BY",
      },
    ],
  },
];
