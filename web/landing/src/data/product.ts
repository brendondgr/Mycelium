/**
 * Copy for the Product page.
 *
 * Keep every claim here traceable to something the platform actually does
 * today — the whole pitch is that Mycelium does not overstate. When a
 * capability ships or changes, update this file rather than adding a second
 * description elsewhere.
 *
 * Write in terms of what the reader gets, not how it is produced. Which
 * databases are ingested, how retrieval is fused, where a language model sits
 * in the ranking — none of that helps a PI decide whether this is worth an
 * afternoon, and publishing it turns a product page into an architecture
 * diagram. The boundaries below are the exception, and they are here because a
 * limit is a promise to the reader rather than an implementation detail.
 */

export const feeds = [
  {
    id: "papers",
    name: "Research papers",
    summary:
      "A daily sweep of the literature, scored against every research theme in your profile rather than one flat keyword list.",
    details: [
      "A lab working on three things gets three separate reads, not one blurred average",
      "Each paper says which of your themes it belongs to, and which others it bridges",
      "The strongest matches arrive with a written reason and a percent fit",
    ],
  },
  {
    id: "grants",
    name: "Grants",
    summary:
      "Funding calls matched to the scope, timing, and team behind each project — not just to your field.",
    details: [
      "Scored against whichever profile you are reading as: yours, a lab's, or one project's",
      "Deadlines tracked per submission kind, and the reminder moves when a date does",
      "Amounts and due dates stated as numbers on the card, not as adjectives",
    ],
  },
  {
    id: "fellowships",
    name: "Fellowships",
    summary:
      "Eligibility is settled before anything is ranked, so you never read about an award you cannot apply for.",
    details: [
      "Citizenship, career stage, field, and restrictions checked as rules, never guessed",
      "Research fit is scored separately, so a strong fit never papers over a hard block",
      "A trainee's eligibility details stay private unless they opt in to lab visibility",
    ],
  },
  {
    id: "conferences",
    name: "Conferences",
    summary:
      "Submission windows tracked as their own dates, because an abstract deadline and an event date are not the same problem.",
    details: [
      "Abstract and full-paper deadlines tracked separately from the event itself",
      "Filterable by what is still open, deadline window, region, and subject",
      "Passed deadlines drop out of the digest on their own",
    ],
  },
] as const;

export const beyondFeeds = [
  {
    title: "A written daily report",
    description:
      "Mylo writes one brief each morning covering everything you watch — papers, grants, fellowships, conferences — with the day's genuinely new items and a showcase of the strongest matches. Labs get their own report alongside personal ones.",
  },
  {
    title: "Projects and shared context",
    description:
      "Give a project its own research focus and it gets its own scored feed. Teams share saves and reading lists, paste in a DOI or a link to pull an item into the project, and what the team reads shapes what the project surfaces next.",
  },
  {
    title: "Deadlines that reach you",
    description:
      "Save an opportunity and set reminders at any offsets you choose. They arrive as in-app notifications and, if you connect Discord, as a direct message or a post in your lab's channel. If a deadline moves, the reminder moves and says so.",
  },
  {
    title: "Search when you need it",
    description:
      "The daily feeds are push. Search is pull — one pass over everything Mycelium has gathered, for the days you already know what you are looking for.",
  },
] as const;

export const limits = [
  {
    title: "It does not write your proposal",
    description:
      "Mycelium gathers evidence, scores fit, and tracks deadlines. The argument is still yours to make.",
  },
  {
    title: "It does not hide a weak match",
    description:
      "Borderline items are labelled borderline. Eligibility that needs a human check says so on the card rather than being rounded up.",
  },
  {
    title: "It does not leak between people",
    description:
      "Lab data is scoped per person and per object. A trainee's citizenship and stage are never exposed to the lab without an explicit opt-in.",
  },
  {
    title: "It does not act without you",
    description:
      "Nothing is submitted, sent, or published on your behalf. Every recommendation is a suggestion waiting on a human decision.",
  },
] as const;
