/**
 * Copy for the front page. Every claim here has to be true of the product;
 * sample content (the report, the card) is fictional and labelled as such
 * where it appears.
 */
import { feedTabs } from "@/data/feed-preview";

/**
 * How it works: one night of the nightly run, as stops on a clock. The stops
 * are the run's real stages in their real order (`make tools-plan`: rank,
 * remind, announce, brief, deliver); the hours are a sample night, since the
 * operator sets when the run starts. `at` is hours after 22:00.
 */
export const night = [
  { at: 0, time: "22:00", title: "The brief", text: "Your themes, projects and people: what tonight is ranked against." },
  { at: 1.5, time: "23:30", title: "New arrivals", text: "Fresh papers, calls and conference deadlines, deduplicated across sources." },
  { at: 3, time: "01:00", title: "Every theme ranked again", text: "The whole corpus, against each theme. Only what newly makes the cut moves on." },
  { at: 4.5, time: "02:30", title: "Reminders", text: "A saved item with a deadline coming up gets its reminder, in the app or in Discord." },
  { at: 6, time: "04:00", title: "New calls announced", text: "Each one a thread in the lab's Discord forums; a changed call updates its thread." },
  { at: 8, time: "06:00", title: "The report", text: "Mylo's written pass, theme by theme: in the app, as a PDF, and in the lab's Discord." },
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
      "Mycelium is open source. The whole stack — web app, API, workers and database — runs in Docker on your own machine or server. make setup asks who it is for, writes the config and secrets, and creates the first admin.",
    commands: [
      "git clone https://github.com/brendondgr/Mycelium.git",
      "cd Mycelium",
      "make setup",
    ],
  },
} as const;
