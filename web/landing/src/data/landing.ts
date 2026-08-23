import type { LucideIcon } from "lucide-react";
import { Bell, Compass, GraduationCap, Network, Search, Users } from "lucide-react";

export const features = [
  {
    title: "Literature discovery",
    description:
      "Surface papers aligned to lab goals with semantic search and weekly pulse summaries.",
    icon: Search,
  },
  {
    title: "Knowledge connections",
    description:
      "Map claims, methods, datasets, and contradictions in an evidence graph your team can review.",
    icon: Network,
  },
  {
    title: "Grant alerts",
    description:
      "Match funding calls to projects and timelines with explainable fit signals.",
    icon: Bell,
  },
  {
    title: "Fellowship matching",
    description:
      "Pair trainees with fellowships that fit skills, eligibility, and career direction.",
    icon: GraduationCap,
  },
  {
    title: "Research strategy",
    description:
      "Turn evidence into next actions for proposals, publications, and collaborations.",
    icon: Compass,
  },
  {
    title: "Team guidance",
    description:
      "Keep PIs, students, and administrators aligned on priorities without inbox chaos.",
    icon: Users,
  },
] as const satisfies ReadonlyArray<{
  title: string;
  description: string;
  icon: LucideIcon;
}>;

/**
 * One preview card. The field names track the workspace card they stand in
 * for — `SuggestionCard`, `GrantCard`, `FellowshipCard`, `ConferenceCard` in
 * `web/app/src/components/portal/sections/` — so the two stay comparable when
 * either side changes.
 */
export type FeedItem = {
  title: string;
  /** First meta line: source · venue for papers, the sponsor for grants. */
  meta?: string;
  /** Second meta line: the byline, or "Posted <date>" on an opportunity. */
  submeta?: string;
  /** The listing's own blurb, above Mylo's reason — the card's `description`. */
  description?: string;
  /** The "why this matched" line — never omit it; it is the whole point. */
  reason: string;
  /** Mylo's verdict, exactly as the app's chip shows it. There is no percentage
   * here or in the product: the number implied a measurement nobody made. */
  fit: "read" | "skim" | "file";
  /** Its place in the theme that surfaced it, shown in the card's gutter. Never
   * a global rank — scores from two themes are not comparable, so a position
   * only means something inside one theme. */
  rank?: number;
  /**
   * Eligibility tier, for fellowships only. In the app this is a deterministic
   * rule-engine verdict shown in the badge row, and it is a hard gate rather
   * than a degree — it is never folded into Mylo's research-fit verdict.
   */
  eligibility?: "Qualified" | "Possible fit" | "Not eligible";
  /** Fellowships: the award class chip ("Predoctoral", "Postdoctoral", …). */
  awardClass?: string;
  /** True when Mylo (the language model) wrote the reason. */
  byMylo?: boolean;
  /** True while the item is a fresh entrant to the reader's Top-25 slate. */
  isNew?: boolean;
  cluster: string;
  clusterToken: string;
  /** Papers: the other clusters this one also reaches into. */
  bridge?: string;
  /** The actionable deadline, in the card's right-hand column. */
  due?: string;
  /** Funding amount, beneath the deadline. */
  amount?: string;
  /** Conferences: where the event is held, and when. */
  where?: string;
  when?: string;
  /** Conferences: which submission windows are still open. */
  open?: readonly string[];
  /** Conferences: the venue's subject chips. */
  subjects?: readonly string[];
};

export type FeedTab = {
  id: string;
  label: string;
  blurb: string;
  /** The card's footer link, e.g. "Read paper" / "View opportunity". */
  linkLabel: string;
  items: FeedItem[];
};

/**
 * Illustrative feed content for the public site. Fictional by design — the
 * real feeds are lab-scoped and permission-gated, so nothing real can appear
 * here. Shapes mirror the live cards in the app so the preview stays honest.
 */
export const feedTabs: readonly FeedTab[] = [
  {
    id: "papers",
    label: "Papers",
    blurb: "Scored against every research cluster in the lab profile, refreshed daily.",
    linkLabel: "Read paper",
    items: [
      {
        title: "Retrieval-grounded clinical decision support under distribution shift",
        meta: "OpenAlex · Nature Machine Intelligence",
        submeta: "2026 · Okonkwo et al.",
        description:
          "Evaluates retrieval-augmented decision support across four hospital systems, and reports where grounding degrades once the deployment population drifts away from the index corpus.",
        reason:
          "Matches your Retrieval grounding cluster and shares the MIMIC-IV dataset with Clinical CDS safety.",
        fit: "read",
        rank: 1,
        byMylo: true,
        isNew: true,
        cluster: "Retrieval grounding",
        clusterToken: "1",
      },
      {
        title: "Contrastive pretraining for sparse neural recordings",
        meta: "bioRxiv · preprint",
        submeta: "2026 · Halvorsen et al.",
        description:
          "A contrastive objective for high-density probe data that holds up when only a few hundred labelled trials are available per animal.",
        reason:
          "Strengthens the readout argument in your Q3 proposal; method overlaps two saved papers.",
        fit: "skim",
        rank: 2,
        byMylo: true,
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
      },
      {
        title: "Limits of multi-hop verification in clinical question answering",
        meta: "PubMed · JAMIA",
        submeta: "2025 · Reyes et al.",
        reason:
          "Bridges two of your clusters — retrieval grounding and clinical CDS safety.",
        fit: "skim",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        bridge: "Clinical CDS safety",
      },
    ],
  },
  {
    id: "grants",
    label: "Grants",
    blurb: "Funding calls matched to project scope, timing, and team composition.",
    linkLabel: "View opportunity",
    items: [
      {
        title: "Smart Health and Biomedical Research in the Era of AI",
        meta: "National Science Foundation",
        submeta: "Posted Mar 4",
        description:
          "Full proposals for interdisciplinary work joining computing research with a named clinical partner. No preliminary award history required.",
        reason:
          "Scope fits Clinical CDS safety; your last two awards sit inside the stated budget band.",
        fit: "read",
        byMylo: true,
        isNew: true,
        cluster: "Clinical CDS safety",
        clusterToken: "3",
        due: "Due Sep 1",
        amount: "$1.2M / 4 yrs",
      },
      {
        title: "R21 Exploratory/Developmental Research Award",
        meta: "National Institutes of Health",
        submeta: "Posted Feb 16",
        reason:
          "Matches the pilot-scale framing of your plasticity work; no preliminary data required.",
        fit: "skim",
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
        due: "Due Oct 16",
        amount: "$275K / 2 yrs",
      },
    ],
  },
  {
    id: "fellowships",
    label: "Fellowships",
    blurb:
      "Eligibility checked by a deterministic rule engine before anything is ranked.",
    linkLabel: "View fellowship",
    items: [
      {
        title: "NSF Graduate Research Fellowship Program",
        meta: "National Science Foundation",
        submeta: "Posted Jul 30",
        description:
          "Three years of support across a five-year window for graduate students in NSF-supported fields, awarded on the strength of the applicant rather than a project.",
        reason:
          "Citizenship, stage, and field all clear for two members. Research fit checked separately.",
        fit: "read",
        eligibility: "Qualified",
        awardClass: "Predoctoral",
        byMylo: true,
        isNew: true,
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
        due: "Due Oct 20",
        amount: "$37K / yr",
      },
      {
        title: "Ford Foundation Predoctoral Fellowship",
        meta: "National Academies of Sciences",
        submeta: "Posted Jun 11",
        reason:
          "Field match is strong, but institutional support needs confirming before applying.",
        fit: "file",
        eligibility: "Possible fit",
        awardClass: "Predoctoral",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        due: "Due Dec 12",
        amount: "$27K / yr",
      },
    ],
  },
  {
    id: "conferences",
    label: "Conferences",
    blurb: "Submission windows tracked separately from event dates, with reminders.",
    linkLabel: "View venue",
    items: [
      {
        title: "NeurIPS — Datasets & Benchmarks Track",
        where: "San Diego, USA · in person",
        when: "Dec 6 – Dec 12",
        description:
          "A peer-reviewed track for datasets, benchmarks, and evaluation methodology, reviewed on documentation and reusability as much as on results.",
        reason:
          "Your benchmark work matches the track scope; abstract deadline lands before your defense.",
        fit: "skim",
        byMylo: true,
        isNew: true,
        cluster: "Retrieval grounding",
        clusterToken: "1",
        due: "Abstract due May 11",
        open: ["Abstract open", "Full paper open"],
        subjects: ["Machine learning", "Benchmarks", "Evaluation"],
      },
      {
        title: "AMIA Annual Symposium",
        where: "Washington DC, USA · hybrid",
        when: "Nov 14 – Nov 18",
        reason:
          "Clinical informatics venue with a track that fits the CDS safety project directly.",
        fit: "skim",
        cluster: "Clinical CDS safety",
        clusterToken: "3",
        due: "Full paper due Mar 11",
        open: ["Full paper open"],
        subjects: ["Clinical informatics", "Decision support"],
      },
    ],
  },
];

export const pipeline = [
  {
    step: "01",
    title: "Profile the lab",
    description:
      "Goals, projects, members, methods, and funding priorities become a structured profile — grouped into research clusters Mylo can actually search on.",
  },
  {
    step: "02",
    title: "Monitor the sources",
    description:
      "Scheduled scans read the literature and opportunity feeds every day, deduplicate across sources, and keep only what clears the relevance floor.",
  },
  {
    step: "03",
    title: "Connect the evidence",
    description:
      "Papers, claims, methods, datasets, and contradictions link into a reviewable graph — not a black-box memory your team has to trust blindly.",
  },
  {
    step: "04",
    title: "Act with review",
    description:
      "A written daily report, scored opportunities, and deadline reminders arrive with their reasoning attached, ready for a human to approve or dismiss.",
  },
] as const;

export type Role = {
  id: string;
  label: string;
  headline: string;
  description: string;
  points: readonly string[];
  myloLine: string;
};

export const roles = [
  {
    id: "pi",
    label: "Principal investigators",
    headline: "See the field move without reading everything",
    description:
      "A daily written brief covering what changed, which funding fits the roadmap, and where the lab should push next — with sources attached.",
    points: [
      "Cross-category daily report grounded in your lab's own profile",
      "Grant fit scored against project scope, timing, and team",
      "Per-project feeds, so a side project does not drown the main line of work",
    ],
    myloLine: "I found 12 papers relevant to your lab goals this morning, across three clusters.",
  },
  {
    id: "trainees",
    label: "Students & postdocs",
    headline: "Find the work and the funding that fit you",
    description:
      "Personal feeds scored on your own interests, plus fellowship matching that checks eligibility before it ever raises your hopes.",
    points: [
      "Your own research clusters, separate from the lab's",
      "Fellowship eligibility checked by rule, not by guesswork",
      "Conference submission windows tracked with reminders",
    ],
    myloLine: "This fellowship matches your field and stage. Verify institutional support before applying.",
  },
  {
    id: "writers",
    label: "Grant writers",
    headline: "Evidence ready before the deadline gets close",
    description:
      "Deadline-aware opportunity lists with the prior work, claims, and project links you need to build the narrative.",
    points: [
      "Deadlines tracked per submission kind, not one flat date",
      "Prior-work links pulled from the lab's own evidence graph",
      "Reminders delivered to a channel, on your schedule",
    ],
    myloLine: "The NSF deadline moved. I have updated the reminder and flagged the change.",
  },
  {
    id: "admins",
    label: "Lab administrators",
    headline: "Coordinate without chasing people",
    description:
      "Shared saves, lab-wide reminders, and member coverage in one workspace, with permissions that respect who should see what.",
    points: [
      "Shared lab saves and reading lists, scoped by role",
      "Reminders routed to the lab's Discord channel",
      "Member and seat management with an audit trail",
    ],
    myloLine: "Three deadlines land in the next 30 days. Two have no owner assigned yet.",
  },
] as const satisfies ReadonlyArray<Role>;

export const trustTenets = [
  {
    title: "Grounded in sources",
    description:
      "Every recommendation carries the item it came from, the interests it matched, and the score that got it there. No unattributed claims.",
  },
  {
    title: "Permission-aware",
    description:
      "Lab data is scoped per object. A trainee's eligibility details stay private unless they opt in to sharing them with the lab.",
  },
  {
    title: "Honest about uncertainty",
    description:
      "When eligibility needs a human check or a match is borderline, Mycelium says so plainly instead of rounding it up to confidence.",
  },
] as const;

export const myloLines = [
  "I found 12 papers relevant to your lab goals this morning.",
  "This fellowship matches your field and stage — verify institutional support.",
  "The NSF deadline moved by two weeks. Your reminder is updated.",
] as const;
