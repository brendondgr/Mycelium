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
 * Sources Mycelium actually ingests today. Keep this list honest — it is a
 * trust claim, not a wish list. Add a source here only once its scraper is
 * live in `apps/scraper`.
 */
export const sources = [
  "OpenAlex",
  "PubMed",
  "Semantic Scholar",
  "ProQuest Pivot",
  "Illinois Fellowship Finder",
] as const;

export type FeedItem = {
  title: string;
  meta: string;
  /** The "why this matched" line — never omit it; it is the whole point. */
  reason: string;
  /** Numeric fit, or a qualitative verdict where a percent would overclaim. */
  score: string;
  scoreLabel: string;
  cluster: string;
  clusterToken: string;
  flag?: string;
};

export type FeedTab = {
  id: string;
  label: string;
  blurb: string;
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
    items: [
      {
        title: "Retrieval-grounded clinical decision support under distribution shift",
        meta: "Nature Machine Intelligence · 4 days ago",
        reason:
          "Matches your Retrieval grounding cluster and shares the MIMIC-IV dataset with Clinical CDS safety.",
        score: "92%",
        scoreLabel: "match",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        flag: "New",
      },
      {
        title: "Contrastive pretraining for sparse neural recordings",
        meta: "bioRxiv preprint · 6 days ago",
        reason:
          "Strengthens the readout argument in your Q3 proposal; method overlaps two saved papers.",
        score: "84%",
        scoreLabel: "match",
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
      },
      {
        title: "Limits of multi-hop verification in clinical question answering",
        meta: "JAMIA · 9 days ago",
        reason:
          "Bridges two of your clusters — retrieval grounding and clinical CDS safety.",
        score: "78%",
        scoreLabel: "match",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        flag: "Bridges 2 clusters",
      },
    ],
  },
  {
    id: "grants",
    label: "Grants",
    blurb: "Funding calls matched to project scope, timing, and team composition.",
    items: [
      {
        title: "NSF Smart Health and Biomedical Research in the Era of AI",
        meta: "National Science Foundation · full proposal",
        reason:
          "Scope fits Clinical CDS safety; your last two awards sit inside the stated budget band.",
        score: "88%",
        scoreLabel: "fit",
        cluster: "Clinical CDS safety",
        clusterToken: "3",
        flag: "Due in 18 days",
      },
      {
        title: "NIH R21 Exploratory/Developmental Research Award",
        meta: "National Institutes of Health · standard due date",
        reason:
          "Matches the pilot-scale framing of your plasticity work; no preliminary data required.",
        score: "74%",
        scoreLabel: "fit",
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
        flag: "Due in 46 days",
      },
    ],
  },
  {
    id: "fellowships",
    label: "Fellowships",
    blurb:
      "Eligibility checked by a deterministic rule engine before anything is ranked.",
    items: [
      {
        title: "NSF Graduate Research Fellowship Program",
        meta: "Trainee award · annual cycle",
        reason:
          "Citizenship, stage, and field all clear for two members. Research fit checked separately.",
        score: "Qualified",
        scoreLabel: "eligibility",
        cluster: "Plasticity mechanisms",
        clusterToken: "2",
        flag: "2 members eligible",
      },
      {
        title: "Ford Foundation Predoctoral Fellowship",
        meta: "Trainee award · annual cycle",
        reason:
          "Field match is strong, but institutional support needs confirming before applying.",
        score: "Review",
        scoreLabel: "eligibility",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        flag: "Needs human check",
      },
    ],
  },
  {
    id: "conferences",
    label: "Conferences",
    blurb: "Submission windows tracked separately from event dates, with reminders.",
    items: [
      {
        title: "NeurIPS — Datasets & Benchmarks Track",
        meta: "San Diego, USA · December",
        reason:
          "Your benchmark work matches the track scope; abstract deadline lands before your defense.",
        score: "81%",
        scoreLabel: "fit",
        cluster: "Retrieval grounding",
        clusterToken: "1",
        flag: "Abstract due in 12 days",
      },
      {
        title: "AMIA Annual Symposium",
        meta: "Washington DC, USA · November",
        reason:
          "Clinical informatics venue with a track that fits the CDS safety project directly.",
        score: "76%",
        scoreLabel: "fit",
        cluster: "Clinical CDS safety",
        clusterToken: "3",
        flag: "Full paper due in 31 days",
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
