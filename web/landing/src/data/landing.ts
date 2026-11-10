/**
 * Copy for the front page. Every claim here has to be true of the product;
 * sample content (the report, the card) is fictional and labelled as such
 * where it appears.
 */
import { feedTabs } from "@/data/feed-preview";

/**
 * What Mycelium covers, catalogue-style. `glyph` is one small line drawing in a
 * 48-unit box; it draws itself in when the entry arrives.
 */
export const features = [
  {
    title: "Literature discovery",
    description:
      "Papers matched to your lab's themes, each with the reason it fits and the strongest reason it might not.",
    glyph: "M8 14c6-3 12-3 16 1v24c-4-4-10-4-16-1z M40 14c-6-3-12-3-16 1v24c4-4 10-4 16-1z",
  },
  {
    title: "Knowledge connections",
    description:
      "Claims, methods, datasets and contradictions linked into an evidence graph your team can review.",
    glyph: "M12 34 24 14 36 30 12 34 M12 34a3 3 0 1 0 0 .1 M24 14a3 3 0 1 0 0 .1 M36 30a3 3 0 1 0 0 .1",
  },
  {
    title: "Grant alerts",
    description:
      "Funding calls matched to projects and timelines, with deadlines tracked per round rather than one flat date.",
    glyph: "M24 40c-7 0-12-5-12-12s5-12 12-12 12 5 12 12-5 12-12 12z M24 16c0-6 4-9 9-9-1 5-4 8-9 9",
  },
  {
    title: "Fellowship matching",
    description:
      "Eligibility checked by rule before it raises anyone's hopes, and named plainly when a human still has to check.",
    glyph: "M24 42V8 M24 14c-5-1-8 1-10 4 M24 14c5-1 8 1 10 4 M24 22c-6-1-10 1-12 5 M24 22c6-1 10 1 12 5 M24 30c-6-1-9 1-11 5 M24 30c6-1 9 1 11 5",
  },
  {
    title: "Daily reports",
    description:
      "One written pass through the night, by theme — in the app, as a PDF, or posted to your lab's Discord.",
    glyph: "M14 8h16l6 6v26H14z M30 8v6h6 M19 22h12 M19 28h12 M19 34h8",
  },
  {
    title: "Labs, people and projects",
    description:
      "Personal, lab and project profiles, each with its own themes, so a side project never drowns the main line of work.",
    glyph: "M8 26c0-6 5-10 10-10s10 4 10 10z M18 26v12 M27 31c0-4 3-7 7-7s7 3 7 7z M34 31v7 M5 38h38",
  },
] as const;

/** The nightly loop, told as one night. */
export const night = [
  {
    time: "22:00",
    title: "Your profile is the brief",
    description:
      "Goals, projects, members and methods become a structured profile, grouped into research themes Mylo can actually search on.",
  },
  {
    time: "02:00",
    title: "Mylo reads the sources",
    description:
      "Scheduled scans read the literature and opportunity feeds, deduplicate across sources, and keep only what clears the relevance floor.",
  },
  {
    time: "04:00",
    title: "The evidence connects",
    description:
      "Papers, claims, methods and datasets link into a graph your team can review — not a black-box memory you have to trust blindly.",
  },
  {
    time: "06:00",
    title: "A report is waiting",
    description:
      "A written report, matched opportunities and deadline reminders, each with its reasoning attached and ready for a human to act on.",
  },
] as const;

/** The sample 06:00 report. Positions and verdicts belong in a report, never in the feed. */
export const reportLines = [
  {
    kind: "lead",
    text: "Good morning. Two of your themes moved overnight, and one deadline is getting close.",
  },
  { kind: "theme", text: "Retrieval grounding" },
  {
    kind: "item",
    text: feedTabs[0].items[0].title,
    rank: "1st in Retrieval grounding",
    verdict: "Read",
  },
  {
    kind: "caveat",
    text: "Worth knowing: every site is an academic medical centre — it says nothing about the community-hospital deployment your grant is scoped to.",
  },
  { kind: "theme", text: "Plasticity mechanisms" },
  {
    kind: "item",
    text: feedTabs[0].items[1].title,
    rank: "2nd in Plasticity mechanisms",
    verdict: "Skim",
  },
  {
    kind: "deadline",
    text: "Smart Health and Biomedical Research in the Era of AI — application closes in 18 days.",
  },
] as const satisfies ReadonlyArray<{
  kind: "lead" | "theme" | "item" | "caveat" | "deadline";
  text: string;
  rank?: string;
  verdict?: "Read" | "Skim";
}>;

/**
 * The parts of one paper card, in the order a reader meets them. `targets`
 * are the card's own class names; the spotlight frames all of them at once.
 */
export const anatomy = [
  {
    id: "match",
    label: "How close it is",
    note: "The embedding similarity between the item and your research — measured, never a model's guess. Hover or focus it for the split by theme.",
    targets: [".fc-match-btn"],
  },
  {
    id: "item",
    label: "The item",
    note: "The paper itself — its title, where it was published, the authors and the year — linked to the source record and never paraphrased away from it.",
    targets: [".fc-title", ".fc-lines"],
  },
  {
    id: "reason",
    label: "Why it fits",
    note: "Mylo's reading, tied to your lab's own work; his portrait marks the ones he wrote. A feed shows it on one line; open the item for his whole take, with the strongest reason it might not be worth your time.",
    targets: [".fc-why"],
  },
  {
    id: "themes",
    label: "The themes it matched",
    note: "Which of your research themes pulled it in, each with its share of the match. There is no global rank: scores from two themes are not comparable.",
    targets: [".fc-topics"],
  },
  {
    id: "tools",
    label: "What you do with it",
    note: "Save it, set a reminder on a deadline, or ignore it and it will not come back. Papers have no deadline, so no reminder.",
    targets: [".fc-tools"],
  },
] as const;

/** Two ways in. */
export const ways = {
  hosted: {
    title: "Use it here",
    description:
      "Sign up on this site with a sign-up code and use the hosted workspace for free. Your first feed is scored as soon as your profile exists.",
    steps: [
      "Sign up with your code",
      "Import your publications or describe your work",
      "Read your first feed the same day",
    ],
  },
  selfHost: {
    title: "Run it yourself",
    description:
      "Mycelium is open source. The whole stack — web app, API, workers and database — starts with Docker Compose on your own machine or server.",
    commands: [
      "git clone https://github.com/brendondgr/Mycelium.git",
      "cd Mycelium",
      "docker compose up",
    ],
  },
} as const;
