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
