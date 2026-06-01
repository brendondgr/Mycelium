import type { LucideIcon } from "lucide-react";
import {
  Bell,
  BookOpen,
  Compass,
  GraduationCap,
  Network,
  Search,
  Users,
} from "lucide-react";

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

export const howItWorks = [
  {
    step: "01",
    title: "Define the lab profile",
    description:
      "Capture goals, projects, members, methods, and funding priorities so recommendations stay specific.",
  },
  {
    step: "02",
    title: "Monitor what matters",
    description:
      "Track literature, grants, fellowships, and field changes with permission-aware scans and digests.",
  },
  {
    step: "03",
    title: "Connect the evidence",
    description:
      "Build a reviewable graph of papers, claims, limitations, and relationships—not a black-box memory.",
  },
  {
    step: "04",
    title: "Act with review",
    description:
      "Receive opportunity alerts, report drafts, and strategic next steps grounded in sources.",
  },
] as const;

export const useCases = [
  {
    title: "Principal investigators",
    description:
      "See what changed in the field, which grants fit the roadmap, and where the lab should focus next.",
    icon: BookOpen,
  },
  {
    title: "Students and postdocs",
    description:
      "Discover literature, fellowship paths, and project angles tied to their skills and interests.",
    icon: GraduationCap,
  },
  {
    title: "Grant writers",
    description:
      "Pull evidence-backed narratives, prior work links, and deadline-aware opportunity lists.",
    icon: Bell,
  },
  {
    title: "Lab administrators",
    description:
      "Coordinate deadlines, member coverage, and reporting without losing context across tools.",
    icon: Users,
  },
] as const;

/** Fictional preview data for the public marketing dashboard. */
export const dashboardPreview = {
  pulse: {
    label: "Research pulse",
    items: [
      { title: "12 new papers", detail: "aligned to synaptic plasticity goals" },
      { title: "3 strengthened claims", detail: "support the Q3 proposal angle" },
      { title: "2 contradictions", detail: "flagged for team review" },
    ],
  },
  connections: {
    label: "Knowledge connections",
    summary: "18 new links this week across methods, datasets, and claims.",
    nodes: ["RAG evaluation", "MIMIC-IV", "Clinical CDS", "Multi-hop QA"],
  },
  opportunities: {
    label: "Opportunity alerts",
    items: [
      { title: "NSF pilot grant", fit: "Strong fit", tone: "accent" as const },
      { title: "NIH training fellowship", fit: "Review eligibility", tone: "muted" as const },
    ],
  },
  projects: {
    label: "Project snapshots",
    items: [
      { name: "Plasticity mechanisms", status: "Literature review in progress" },
      { name: "Clinical CDS safety", status: "Grant draft due in 18 days" },
    ],
  },
  nextActions: {
    label: "Next actions",
    items: [
      "Compare three papers on retrieval grounding for the proposal.",
      "Schedule a fellowship review for the first-year trainee cohort.",
      "Approve the weekly evidence digest before Monday stand-up.",
    ],
  },
};
