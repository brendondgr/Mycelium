/**
 * Fictional content for the Labs preview. Field shapes follow the real feeds
 * (theme, reason, caveat, source; deadlines and eligibility on grants) and,
 * like the app's feed cards, carry no score, percent, position or verdict.
 */

export type Scope = {
  id: string;
  kind: "personal" | "lab" | "department";
  name: string;
  short: string;
  hint: string;
};

export const SCOPES: Scope[] = [
  { id: "me", kind: "personal", name: "Just me", short: "Me", hint: "Your own feeds" },
  { id: "pulse", kind: "lab", name: "Pulse Lab", short: "PL", hint: "6 members · PI" },
  { id: "coastal", kind: "lab", name: "Coastal Dynamics Lab", short: "CD", hint: "11 members" },
  {
    id: "dept",
    kind: "department",
    name: "Dept. of Scientific Computing",
    short: "SC",
    hint: "14 labs",
  },
];

export type Theme = { id: string; label: string; tone: number };

export const THEMES: Theme[] = [
  { id: "agents", label: "Clinical AI agents", tone: 1 },
  { id: "ocean", label: "Ocean state forecasting", tone: 3 },
  { id: "retrieval", label: "Retrieval for science", tone: 5 },
  { id: "uq", label: "Uncertainty in emulators", tone: 6 },
];

export type Paper = {
  id: string;
  title: string;
  venue: string;
  authors: string;
  theme: string;
  found: "today" | "yesterday" | "this week";
  reason: string;
  caveat: string;
  abstract: string;
};

export const PAPERS: Paper[] = [
  {
    id: "p1",
    title: "Tool-using agents for discharge summaries: a prospective audit across three hospitals",
    venue: "medRxiv",
    authors: "Okafor, Lindqvist, Ruiz et al.",
    theme: "agents",
    found: "today",
    reason:
      "Audits the same hand-off step your triage-agent project automates, with the error taxonomy you were missing.",
    caveat: "Single vendor model; results may not transfer to open-weight agents.",
    abstract:
      "We deployed a tool-calling agent to draft discharge summaries and audited 2,140 drafts against clinician edits, classifying 11 failure modes.",
  },
  {
    id: "p2",
    title: "Learned data assimilation for mesoscale eddies with sparse Argo profiles",
    venue: "JAMES",
    authors: "Haugen, Mbeki, Tanaka",
    theme: "ocean",
    found: "today",
    reason:
      "Same Gulf domain and observation sparsity as your SSH-reconstruction work; reports skill at 7-day lead.",
    caveat: "Evaluated on reanalysis, not withheld in-situ data.",
    abstract:
      "A neural assimilation operator trained on 20 years of reanalysis reconstructs eddy fields from fewer than 40 profiles per day.",
  },
  {
    id: "p3",
    title: "Short queries break cross-encoders: a reproducibility study on scholarly search",
    venue: "SIGIR",
    authors: "Brandt, Iyer",
    theme: "retrieval",
    found: "today",
    reason:
      "Independent replication of the short-query failure you measured; useful as a citation for the evaluation write-up.",
    caveat: "English-only corpora.",
    abstract:
      "Across four benchmarks, cross-encoder rerankers lose to BM25 on queries of one to four words.",
  },
  {
    id: "p4",
    title: "Calibrated ensembles for ocean emulators via conformal residuals",
    venue: "arXiv",
    authors: "Rossi, Chen, Abara",
    theme: "uq",
    found: "yesterday",
    reason: "Gives a cheap interval method you could drop onto the existing emulator without retraining.",
    caveat: "Assumes exchangeable errors; seasonal drift is not tested.",
    abstract:
      "Conformal prediction on emulator residuals yields intervals with nominal coverage at a fraction of ensemble cost.",
  },
  {
    id: "p5",
    title: "When should a clinical agent ask? Deferral policies under label noise",
    venue: "NeurIPS",
    authors: "Weiss, Adeyemi",
    theme: "agents",
    found: "yesterday",
    reason: "Frames the 'ask a clinician' decision your agent hard-codes as a learnable policy.",
    caveat: "Simulated clinicians only.",
    abstract:
      "We study learned deferral for tool-using agents and show policies robust to 30% label noise.",
  },
  {
    id: "p6",
    title: "Benchmarking sea-surface height super-resolution: SWOT as ground truth",
    venue: "GRL",
    authors: "Fontaine, Kim, Osei",
    theme: "ocean",
    found: "this week",
    reason: "First benchmark that scores against SWOT swaths — the comparison your reviewers asked for.",
    caveat: "Covers one SWOT cycle.",
    abstract:
      "We release a benchmark of 14 super-resolution methods scored against SWOT KaRIn observations.",
  },
];

export type Grant = {
  id: string;
  title: string;
  funder: string;
  theme: string;
  closesIn: number;
  closesOn: string;
  month: string;
  amount: string;
  status: "new" | "closing" | "saved";
  reason: string;
  checks: { label: string; ok: boolean | null }[];
};

export const GRANTS: Grant[] = [
  {
    id: "g1",
    title: "Trustworthy AI in Clinical Decision Support",
    funder: "NIH · NLM",
    theme: "agents",
    closesIn: 9,
    closesOn: "Nov 16",
    month: "November",
    amount: "$1.2M over 4 years",
    status: "closing",
    reason: "Calls for audited agent deployments — your discharge-summary pilot is the preliminary data.",
    checks: [
      { label: "US institution", ok: true },
      { label: "Clinical partner letter", ok: null },
    ],
  },
  {
    id: "g2",
    title: "Physical Oceanography — Observing System Design",
    funder: "NSF · OCE",
    theme: "ocean",
    closesIn: 23,
    closesOn: "Nov 30",
    month: "November",
    amount: "$650K over 3 years",
    status: "new",
    reason: "Explicitly invites ML-based observing-system experiments in the Gulf.",
    checks: [
      { label: "PI eligibility", ok: true },
      { label: "Ship time not required", ok: true },
    ],
  },
  {
    id: "g3",
    title: "Open Research Infrastructure Seed",
    funder: "Sloan Foundation",
    theme: "retrieval",
    closesIn: 41,
    closesOn: "Dec 18",
    month: "December",
    amount: "$250K",
    status: "saved",
    reason: "Funds open-source scholarly tooling with a public evaluation story.",
    checks: [
      { label: "Open licence", ok: true },
      { label: "Letter of inquiry first", ok: null },
    ],
  },
  {
    id: "g4",
    title: "Uncertainty Quantification for Earth System Models",
    funder: "DOE · ASCR",
    theme: "uq",
    closesIn: 66,
    closesOn: "Jan 12",
    month: "January",
    amount: "$900K over 3 years",
    status: "new",
    reason: "Targets emulator calibration specifically; your conformal work fits the second thrust.",
    checks: [
      { label: "National-lab partner", ok: false },
      { label: "PI eligibility", ok: true },
    ],
  },
];

export const FOUND = [
  { key: "papers", label: "papers", today: 12, week: 64 },
  { key: "grants", label: "grants", today: 3, week: 11 },
  { key: "fellowships", label: "fellowships", today: 1, week: 4 },
  { key: "conferences", label: "conferences", today: 2, week: 6 },
] as const;

export const PROJECTS = [
  { id: "pr1", name: "Triage agent pilot", status: "Writing up", moved: "2 new papers this week" },
  { id: "pr2", name: "Gulf SSH reconstruction", status: "Experiments", moved: "Reviewer asked for SWOT comparison" },
  { id: "pr3", name: "Open retrieval eval", status: "Planning", moved: "Quiet for 9 days" },
];

export const SEARCH_SUGGESTIONS = [
  "deferral policies clinical agents",
  "SWOT sea surface height",
  "conformal intervals emulators",
  "BM25 short queries",
];

export const PEOPLE = [
  { name: "Ama Owusu", role: "PhD student · Pulse Lab", why: "Works on SSH reconstruction" },
  { name: "Dr. Lena Brandt", role: "External · TU Delft", why: "Author of the short-query replication" },
];

export function themeOf(id: string): Theme {
  return THEMES.find((t) => t.id === id) ?? THEMES[0];
}
