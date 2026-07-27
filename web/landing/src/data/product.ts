/**
 * Copy for the Product page.
 *
 * Keep every claim here traceable to something the platform actually does
 * today — the whole pitch is that Mycelium does not overstate. When a
 * capability ships or changes, update this file rather than adding a second
 * description elsewhere.
 */

export const feeds = [
  {
    id: "papers",
    name: "Research papers",
    summary:
      "A daily sweep of the literature, scored against every research cluster in your profile rather than one flat keyword list.",
    details: [
      "Reads OpenAlex, PubMed, and Semantic Scholar, deduplicated across sources",
      "Lexical and semantic retrieval fused, so a paper matching several of your interests outranks one matching a single term",
      "Top matches get a written explanation and a percent match; the rest are scored deterministically",
    ],
  },
  {
    id: "grants",
    name: "Grants",
    summary:
      "Funding calls matched to the scope, timing, and team behind each project — not just to your field.",
    details: [
      "Ingested from ProQuest Pivot and refreshed on a schedule",
      "Scored per target: your personal profile, a lab, or an individual project",
      "Deadlines tracked per submission kind, with the date change history kept",
    ],
  },
  {
    id: "fellowships",
    name: "Fellowships",
    summary:
      "Eligibility is decided by a deterministic rule engine before anything is ranked, so you never read about an award you cannot apply for.",
    details: [
      "Citizenship, career stage, field, and restriction rules checked first — no language model in that decision",
      "Research fit scored separately, then blended with eligibility for ranking",
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
      "Filterable by submission status, deadline window, region, and subject",
      "Passed deadlines drop out of the digest automatically",
    ],
  },
] as const;

export const matchSteps = [
  {
    step: "01",
    title: "Your interests become clusters",
    description:
      "Rather than one undifferentiated interest list, Mycelium groups your research into themes, each with its own concrete sub-topics. A lab working on three things gets three separate searches, not one blurred average.",
  },
  {
    step: "02",
    title: "Each cluster searches on its own",
    description:
      "Every cluster runs its own lexical and semantic retrieval over the corpus. Results are fused by rank, so an item strong across several clusters rises — and the cluster that pulled it in is recorded.",
  },
  {
    step: "03",
    title: "Scores are attributed, not averaged away",
    description:
      "Each item keeps the cluster it matched best, plus any others it bridges. That attribution is what lets a card tell you which part of your work it belongs to instead of just asserting relevance.",
  },
  {
    step: "04",
    title: "The strongest matches get explained",
    description:
      "The top of each feed goes to a language model with the item and your profile, which writes the plain-language reason you read on the card. Everything below keeps its deterministic score, and a model outage falls back to that score rather than failing.",
  },
] as const;

export const beyondFeeds = [
  {
    title: "A written daily report",
    description:
      "Mylo writes one cross-category brief each morning covering everything you watch — papers, grants, fellowships, conferences — with counts, the day's genuinely new items, and a showcase of the strongest matches. Labs get their own report alongside personal ones.",
  },
  {
    title: "Projects and shared context",
    description:
      "Give a project its own research focus and it gets its own scored feed. Teams share saves and reading lists, paste in a DOI or link to pull an item into the project, and a member's engagement feeds back into what the project surfaces next.",
  },
  {
    title: "Deadlines that reach you",
    description:
      "Save an opportunity and set reminders at any offsets you choose. They arrive as in-app notifications and, if you connect Discord, as a direct message or a post in your lab's channel. If a deadline moves, the reminder moves and says so.",
  },
  {
    title: "Search when you need it",
    description:
      "The daily feeds are push. Search is pull — one query-first pass over the whole corpus combining full-text, semantic, and fuzzy matching, for the days you already know what you are looking for.",
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
      "Lab-scoped data is permission-checked per object. A trainee's citizenship and stage are never exposed to the lab without an explicit opt-in.",
  },
  {
    title: "It does not act without you",
    description:
      "Nothing is submitted, sent, or published on your behalf. Every recommendation is a suggestion waiting on a human decision.",
  },
] as const;
