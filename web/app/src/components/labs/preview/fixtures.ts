/**
 * Fictional content for the Labs preview.
 *
 * Field shapes follow what the real feeds carry — the matched theme and the
 * themes it also touches, Mylo's written reason and the caveat, who in the lab
 * Mylo suggests and why, the "Can we use this?" checks, key dates, team fit,
 * where it was announced, and the source. Like the app's feed cards (see
 * docs/styles.md, "How a recommendation states itself") nothing here carries a
 * score, percent, position or verdict.
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
  { id: "pulse", kind: "lab", name: "Pulse Lab", short: "PL", hint: "5 members · PI" },
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

export type Member = { id: string; name: string; initials: string; role: string };

export const MEMBERS: Member[] = [
  { id: "ri", name: "Dr. Rosa Iglesias", initials: "RI", role: "PI" },
  { id: "jp", name: "Jun Park", initials: "JP", role: "Postdoc" },
  { id: "ao", name: "Ama Owusu", initials: "AO", role: "PhD student" },
  { id: "pn", name: "Priya Natarajan", initials: "PN", role: "PhD student" },
  { id: "tl", name: "Theo Lindgren", initials: "TL", role: "MS student" },
];

export type Suggested = { member: string; why: string };

export type CheckStatus = "ok" | "warn" | "unknown" | "block";
export type Check = { label: string; status: CheckStatus; note?: string };

type Common = {
  id: string;
  title: string;
  theme: string;
  /** Other themes the item also touches ("Also …" on the real card). */
  also: string[];
  found: "today" | "yesterday" | "this week";
  isNew: boolean;
  saved: boolean;
  /** Mylo wrote the reason (his portrait rides it) vs. the similarity fallback. */
  byMylo: boolean;
  reason: string;
  caveat: string;
  suggested: Suggested[];
  projects: string[];
  source: string;
};

export type Paper = Common & {
  kind: "paper";
  venue: string;
  venueType: "preprint" | "journal" | "conference";
  authors: string;
  published: string;
  abstract: string;
};

export type Grant = Common & {
  kind: "grant";
  funder: string;
  sponsor: string;
  program: string;
  amount: string;
  closesIn: number;
  closesOn: string;
  month: string;
  status: "new" | "closing" | "saved";
  dates: { label: string; when: string }[];
  checks: Check[];
  teamFit: string;
  announced?: string;
};

export type Fellowship = Common & {
  kind: "fellowship";
  sponsor: string;
  amount: string;
  closesIn: number;
  closesOn: string;
  month: string;
  stages: string[];
  citizenship: "any" | "us";
  qualified: boolean;
  checks: Check[];
  dates: { label: string; when: string }[];
};

export type Conference = Common & {
  kind: "conference";
  acronym: string;
  name: string;
  where: string;
  continent: string;
  when: string;
  eventIn: number;
  month: string;
  rank?: string;
  open: boolean;
  closesIn: number;
  closesOn: string;
  deadlines: { label: string; when: string }[];
};

export type FeedItem = Paper | Grant | Fellowship | Conference;
export type FeedKind = FeedItem["kind"];

export const PAPERS: Paper[] = [
  {
    kind: "paper",
    id: "p1",
    title: "Tool-using agents for discharge summaries: a prospective audit across three hospitals",
    venue: "medRxiv",
    venueType: "preprint",
    authors: "Okafor, Lindqvist, Ruiz et al.",
    published: "Nov 6, 2026",
    theme: "agents",
    also: ["retrieval"],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    reason:
      "Audits the same hand-off step your triage-agent project automates, and its 11-mode error taxonomy is the one your write-up is missing.",
    caveat: "Single vendor model; results may not transfer to open-weight agents.",
    suggested: [
      { member: "jp", why: "Runs the triage-agent pilot; the error taxonomy maps onto his evaluation table." },
      { member: "ri", why: "Cited as related work in the lab's current clinical-AI proposal." },
    ],
    projects: ["Triage agent pilot"],
    source: "medrxiv.org",
    abstract:
      "We deployed a tool-calling agent to draft discharge summaries and audited 2,140 drafts against clinician edits, classifying 11 failure modes. Omission of pending results and wrong-tool calls accounted for 61% of clinically significant errors.",
  },
  {
    kind: "paper",
    id: "p2",
    title: "Learned data assimilation for mesoscale eddies with sparse Argo profiles",
    venue: "JAMES",
    venueType: "journal",
    authors: "Haugen, Mbeki, Tanaka",
    published: "Nov 5, 2026",
    theme: "ocean",
    also: ["uq"],
    found: "today",
    isNew: true,
    saved: true,
    byMylo: true,
    reason:
      "Same Gulf domain and observation sparsity as your SSH-reconstruction work, and it reports skill at a 7-day lead — the horizon your reviewers asked about.",
    caveat: "Evaluated on reanalysis, not withheld in-situ data.",
    suggested: [
      { member: "ao", why: "Her SSH reconstruction uses the same Argo subsampling; a direct baseline." },
      { member: "pn", why: "The paper's ensemble spread is a ready test case for her calibration method." },
    ],
    projects: ["Gulf SSH reconstruction"],
    source: "agupubs.onlinelibrary.wiley.com",
    abstract:
      "A neural assimilation operator trained on 20 years of reanalysis reconstructs eddy fields from fewer than 40 profiles per day, outperforming optimal interpolation at 3- and 7-day leads.",
  },
  {
    kind: "paper",
    id: "p3",
    title: "Short queries break cross-encoders: a reproducibility study on scholarly search",
    venue: "SIGIR",
    venueType: "conference",
    authors: "Brandt, Iyer",
    published: "Nov 4, 2026",
    theme: "retrieval",
    also: [],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    reason:
      "An independent replication of the short-query failure you measured — citable support for the evaluation write-up.",
    caveat: "English-only corpora.",
    suggested: [{ member: "tl", why: "Owns the retrieval evaluation; this replicates his main negative result." }],
    projects: ["Open retrieval eval"],
    source: "dl.acm.org",
    abstract:
      "Across four benchmarks, cross-encoder rerankers lose to BM25 on queries of one to four words, while winning on longer natural-language questions.",
  },
  {
    kind: "paper",
    id: "p4",
    title: "Calibrated ensembles for ocean emulators via conformal residuals",
    venue: "arXiv",
    venueType: "preprint",
    authors: "Rossi, Chen, Abara",
    published: "Nov 3, 2026",
    theme: "uq",
    also: ["ocean"],
    found: "yesterday",
    isNew: false,
    saved: false,
    byMylo: false,
    reason: "A cheap interval method you could drop onto the existing emulator without retraining.",
    caveat: "Assumes exchangeable errors; seasonal drift is not tested.",
    suggested: [{ member: "pn", why: "Conformal intervals are the second chapter of her thesis plan." }],
    projects: [],
    source: "arxiv.org",
    abstract:
      "Conformal prediction on emulator residuals yields intervals with nominal coverage at a fraction of ensemble cost.",
  },
  {
    kind: "paper",
    id: "p5",
    title: "When should a clinical agent ask? Deferral policies under label noise",
    venue: "NeurIPS",
    venueType: "conference",
    authors: "Weiss, Adeyemi",
    published: "Nov 2, 2026",
    theme: "agents",
    also: ["uq"],
    found: "yesterday",
    isNew: false,
    saved: false,
    byMylo: true,
    reason: "Frames the “ask a clinician” decision your agent hard-codes as a policy it could learn.",
    caveat: "Simulated clinicians only.",
    suggested: [{ member: "jp", why: "His agent's deferral threshold is a fixed constant today." }],
    projects: ["Triage agent pilot"],
    source: "openreview.net",
    abstract: "We study learned deferral for tool-using agents and show policies robust to 30% label noise.",
  },
  {
    kind: "paper",
    id: "p6",
    title: "Benchmarking sea-surface height super-resolution: SWOT as ground truth",
    venue: "GRL",
    venueType: "journal",
    authors: "Fontaine, Kim, Osei",
    published: "Oct 31, 2026",
    theme: "ocean",
    also: [],
    found: "this week",
    isNew: false,
    saved: true,
    byMylo: true,
    reason: "The first benchmark scored against SWOT swaths — the comparison your reviewers asked for.",
    caveat: "Covers one SWOT cycle.",
    suggested: [{ member: "ao", why: "Reviewer 2 asked her for exactly this comparison." }],
    projects: ["Gulf SSH reconstruction"],
    source: "agupubs.onlinelibrary.wiley.com",
    abstract: "We release a benchmark of 14 super-resolution methods scored against SWOT KaRIn observations.",
  },
];

export const GRANTS: Grant[] = [
  {
    kind: "grant",
    id: "g1",
    title: "Trustworthy AI in Clinical Decision Support",
    funder: "NIH · NLM",
    sponsor: "NIH",
    program: "R01, PAR-26-114",
    theme: "agents",
    also: ["retrieval"],
    found: "this week",
    isNew: false,
    saved: true,
    byMylo: true,
    closesIn: 9,
    closesOn: "Nov 16",
    month: "November",
    amount: "$1.2M over 4 years",
    status: "closing",
    reason: "Calls for audited agent deployments — your discharge-summary pilot is the preliminary data it asks for.",
    caveat: "Needs a named clinical partner; the lab has none on record.",
    suggested: [
      { member: "ri", why: "Lead PI; the call requires a faculty PI with a clinical-AI track record." },
      { member: "jp", why: "Writes the aims around the pilot he runs." },
    ],
    projects: ["Triage agent pilot"],
    source: "grants.nih.gov",
    dates: [
      { label: "Letter of intent", when: "Nov 16" },
      { label: "Full application", when: "Dec 14" },
    ],
    checks: [
      { label: "US institution", status: "ok" },
      { label: "Faculty PI", status: "ok" },
      { label: "Clinical partner letter", status: "warn", note: "Required; none named yet." },
    ],
    teamFit: "The lab covers 3 of the 4 named areas; missing a clinical informatics partner.",
    announced: "#grants · Pulse Lab Discord",
  },
  {
    kind: "grant",
    id: "g2",
    title: "Physical Oceanography — Observing System Design",
    funder: "NSF · OCE",
    sponsor: "NSF",
    program: "Standard grant",
    theme: "ocean",
    also: ["uq"],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    closesIn: 23,
    closesOn: "Nov 30",
    month: "November",
    amount: "$650K over 3 years",
    status: "new",
    reason: "Explicitly invites ML-based observing-system experiments in the Gulf — your reconstruction work's home turf.",
    caveat: "Favours proposals with new in-situ data collection.",
    suggested: [
      { member: "ao", why: "Her reconstruction is the experiment design the call describes." },
      { member: "ri", why: "Would be the PI of record." },
    ],
    projects: ["Gulf SSH reconstruction"],
    source: "nsf.gov",
    dates: [{ label: "Full proposal", when: "Nov 30" }],
    checks: [
      { label: "PI eligibility", status: "ok" },
      { label: "Ship time not required", status: "ok" },
    ],
    teamFit: "Strong: every named expertise area is covered by a current member.",
  },
  {
    kind: "grant",
    id: "g3",
    title: "Open Research Infrastructure Seed",
    funder: "Sloan Foundation",
    sponsor: "Sloan",
    program: "Technology program",
    theme: "retrieval",
    also: [],
    found: "this week",
    isNew: false,
    saved: true,
    byMylo: true,
    closesIn: 41,
    closesOn: "Dec 18",
    month: "December",
    amount: "$250K",
    status: "saved",
    reason: "Funds open-source scholarly tooling with a public evaluation story — which the retrieval eval already has.",
    caveat: "Letter of inquiry first; the full invite rate is low.",
    suggested: [{ member: "tl", why: "Maintains the open evaluation harness the proposal would fund." }],
    projects: ["Open retrieval eval"],
    source: "sloan.org",
    dates: [{ label: "Letter of inquiry", when: "Dec 18" }],
    checks: [
      { label: "Open licence", status: "ok" },
      { label: "Letter of inquiry first", status: "unknown", note: "Template not yet published." },
    ],
    teamFit: "Covered; a co-PI from a second institution would strengthen it.",
    announced: "#funding · Dept. Discord",
  },
  {
    kind: "grant",
    id: "g4",
    title: "Uncertainty Quantification for Earth System Models",
    funder: "DOE · ASCR",
    sponsor: "DOE",
    program: "FOA DE-FOA-0003391",
    theme: "uq",
    also: ["ocean"],
    found: "yesterday",
    isNew: true,
    saved: false,
    byMylo: false,
    closesIn: 66,
    closesOn: "Jan 12",
    month: "January",
    amount: "$900K over 3 years",
    status: "new",
    reason: "Targets emulator calibration specifically; the conformal work fits the second thrust.",
    caveat: "Requires a national-lab partner.",
    suggested: [{ member: "pn", why: "Her calibration method is the second thrust." }],
    projects: [],
    source: "science.osti.gov",
    dates: [
      { label: "Pre-application", when: "Jan 12" },
      { label: "Full application", when: "Mar 2" },
    ],
    checks: [
      { label: "National-lab partner", status: "block", note: "Required; the lab has no such partner." },
      { label: "PI eligibility", status: "ok" },
    ],
    teamFit: "Partial: no national-lab collaborator.",
  },
  {
    kind: "grant",
    id: "g5",
    title: "AI for Coastal Resilience — Seed Awards",
    funder: "NOAA · OAR",
    sponsor: "NOAA",
    program: "Seed award",
    theme: "ocean",
    also: ["agents"],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    closesIn: 12,
    closesOn: "Nov 19",
    month: "November",
    amount: "$150K, 1 year",
    status: "closing",
    reason: "A small, fast award that would fund the SWOT comparison on its own.",
    caveat: "One-year scope; no renewal.",
    suggested: [{ member: "ao", why: "The SWOT comparison is a one-year piece of her thesis." }],
    projects: ["Gulf SSH reconstruction"],
    source: "noaa.gov",
    dates: [{ label: "Application", when: "Nov 19" }],
    checks: [
      { label: "US institution", status: "ok" },
      { label: "Early-career PI preferred", status: "warn", note: "Preference, not a requirement." },
    ],
    teamFit: "Covered.",
  },
];

export const FELLOWSHIPS: Fellowship[] = [
  {
    kind: "fellowship",
    id: "f1",
    title: "Graduate Research Fellowship",
    sponsor: "NSF",
    theme: "ocean",
    also: [],
    found: "this week",
    isNew: false,
    saved: true,
    byMylo: true,
    amount: "$37K stipend + tuition, 3 years",
    closesIn: 13,
    closesOn: "Nov 20",
    month: "November",
    stages: ["PhD"],
    citizenship: "us",
    qualified: true,
    reason: "Ama is in her first two years and a US permanent resident — the window this fellowship needs.",
    caveat: "Highly competitive; the research statement carries most of the weight.",
    suggested: [{ member: "ao", why: "Eligible by stage and citizenship; her SSH work is a strong statement." }],
    projects: ["Gulf SSH reconstruction"],
    source: "nsfgrfp.org",
    checks: [
      { label: "First or second year", status: "ok" },
      { label: "US citizen or permanent resident", status: "ok" },
    ],
    dates: [{ label: "Application", when: "Nov 20" }],
  },
  {
    kind: "fellowship",
    id: "f2",
    title: "Computational Science Graduate Fellowship",
    sponsor: "DOE",
    theme: "uq",
    also: ["ocean"],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    amount: "$45K stipend + tuition, 4 years",
    closesIn: 54,
    closesOn: "Dec 31",
    month: "December",
    stages: ["PhD"],
    citizenship: "us",
    qualified: true,
    reason: "Priya's emulator calibration is squarely the applied-math-plus-domain profile this fellowship funds.",
    caveat: "Requires a programme of study approved by the fellowship.",
    suggested: [{ member: "pn", why: "Eligible; her thesis plan matches the required course mix." }],
    projects: [],
    source: "krellinst.org",
    checks: [
      { label: "Early-stage PhD", status: "ok" },
      { label: "US citizen or permanent resident", status: "ok" },
      { label: "Approved programme of study", status: "unknown" },
    ],
    dates: [{ label: "Application", when: "Dec 31" }],
  },
  {
    kind: "fellowship",
    id: "f3",
    title: "Postdoctoral Fellowship in Responsible AI",
    sponsor: "Schmidt Sciences",
    theme: "agents",
    also: [],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    amount: "$85K salary, 2 years",
    closesIn: 31,
    closesOn: "Dec 8",
    month: "December",
    stages: ["Postdoc"],
    citizenship: "any",
    qualified: true,
    reason: "Jun's deferral and audit work is the exact 'responsible deployment' angle of this call.",
    caveat: "Expects a move to a partner institution for year two.",
    suggested: [{ member: "jp", why: "Within three years of his PhD; no citizenship requirement." }],
    projects: ["Triage agent pilot"],
    source: "schmidtsciences.org",
    checks: [
      { label: "Within 3 years of PhD", status: "ok" },
      { label: "Open to any nationality", status: "ok" },
    ],
    dates: [{ label: "Application", when: "Dec 8" }],
  },
  {
    kind: "fellowship",
    id: "f4",
    title: "Summer Research Internship in Scientific Software",
    sponsor: "Argonne National Laboratory",
    theme: "retrieval",
    also: [],
    found: "yesterday",
    isNew: false,
    saved: false,
    byMylo: false,
    amount: "$9K, 12 weeks",
    closesIn: 70,
    closesOn: "Jan 16",
    month: "January",
    stages: ["MS", "PhD"],
    citizenship: "any",
    qualified: true,
    reason: "Theo's evaluation harness is the kind of open tooling the scientific-software track takes.",
    caveat: "On-site in Illinois for the summer.",
    suggested: [{ member: "tl", why: "MS students are eligible; no citizenship requirement." }],
    projects: ["Open retrieval eval"],
    source: "anl.gov",
    checks: [
      { label: "Enrolled graduate student", status: "ok" },
      { label: "Summer availability", status: "unknown" },
    ],
    dates: [{ label: "Application", when: "Jan 16" }],
  },
  {
    kind: "fellowship",
    id: "f5",
    title: "Early-Career Faculty Fellowship",
    sponsor: "Sloan Foundation",
    theme: "retrieval",
    also: ["agents"],
    found: "this week",
    isNew: false,
    saved: false,
    byMylo: true,
    amount: "$75K, 2 years",
    closesIn: 68,
    closesOn: "Jan 14",
    month: "January",
    stages: ["Faculty"],
    citizenship: "any",
    qualified: false,
    reason: "Fits the lab's direction, but Rosa is past the six-year window.",
    caveat: "Nomination by a department chair required.",
    suggested: [],
    projects: [],
    source: "sloan.org",
    checks: [
      { label: "Within 6 years of first faculty post", status: "block", note: "Rosa is in year 8." },
      { label: "Chair nomination", status: "unknown" },
    ],
    dates: [{ label: "Nomination", when: "Jan 14" }],
  },
];

export const CONFERENCES: Conference[] = [
  {
    kind: "conference",
    id: "c1",
    title: "ACM SIGIR Conference on Research and Development in Information Retrieval",
    acronym: "SIGIR 2027",
    name: "SIGIR",
    theme: "retrieval",
    also: [],
    found: "this week",
    isNew: false,
    saved: true,
    byMylo: true,
    where: "Lisbon, Portugal",
    continent: "Europe",
    when: "Jul 11–15, 2027",
    eventIn: 246,
    month: "July",
    rank: "CORE A*",
    open: true,
    closesIn: 77,
    closesOn: "Jan 23",
    deadlines: [
      { label: "Abstract", when: "Jan 16" },
      { label: "Full paper", when: "Jan 23" },
    ],
    reason: "The short-query result is a natural reproducibility-track paper, and the replication above makes it timely.",
    caveat: "Reproducibility papers are capped at 8 pages.",
    suggested: [
      { member: "tl", why: "First author on the evaluation results." },
      { member: "ri", why: "Senior author; on the SIGIR PC last year." },
    ],
    projects: ["Open retrieval eval"],
    source: "sigir.org",
  },
  {
    kind: "conference",
    id: "c2",
    title: "Ocean Sciences Meeting",
    acronym: "OSM 2027",
    name: "OSM",
    theme: "ocean",
    also: ["uq"],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    where: "New Orleans, USA",
    continent: "North America",
    when: "Feb 22–27, 2027",
    eventIn: 107,
    month: "February",
    open: true,
    closesIn: 19,
    closesOn: "Nov 26",
    deadlines: [{ label: "Abstract", when: "Nov 26" }],
    reason: "Has a session on ML for sea-surface height this cycle — the most direct audience for the SWOT comparison.",
    caveat: "Abstract-only; no proceedings.",
    suggested: [{ member: "ao", why: "Her SWOT comparison fits the ML-for-SSH session." }],
    projects: ["Gulf SSH reconstruction"],
    source: "agu.org",
  },
  {
    kind: "conference",
    id: "c3",
    title: "Machine Learning for Health",
    acronym: "ML4H 2026",
    name: "ML4H",
    theme: "agents",
    also: [],
    found: "yesterday",
    isNew: false,
    saved: false,
    byMylo: true,
    where: "Vancouver, Canada",
    continent: "North America",
    when: "Dec 13, 2026",
    eventIn: 36,
    month: "December",
    open: false,
    closesIn: -20,
    closesOn: "Oct 18",
    deadlines: [{ label: "Paper (closed)", when: "Oct 18" }],
    reason: "Submissions are closed, but attending puts Jun in the room with the audit paper's authors.",
    caveat: "Closed for papers — attendance only.",
    suggested: [{ member: "jp", why: "The audit paper's authors are presenting." }],
    projects: ["Triage agent pilot"],
    source: "ml4h.cc",
  },
  {
    kind: "conference",
    id: "c4",
    title: "International Conference on Learning Representations",
    acronym: "ICLR 2027",
    name: "ICLR",
    theme: "uq",
    also: ["agents"],
    found: "this week",
    isNew: false,
    saved: false,
    byMylo: false,
    where: "Rio de Janeiro, Brazil",
    continent: "South America",
    when: "Apr 24–28, 2027",
    eventIn: 168,
    month: "April",
    rank: "CORE A*",
    open: true,
    closesIn: 88,
    closesOn: "Feb 3",
    deadlines: [{ label: "Workshop papers", when: "Feb 3" }],
    reason: "The uncertainty workshop is the right size for the conformal-emulator result.",
    caveat: "Main track closed; workshops only.",
    suggested: [{ member: "pn", why: "A 4-page workshop paper from her second chapter." }],
    projects: [],
    source: "iclr.cc",
  },
  {
    kind: "conference",
    id: "c5",
    title: "European Geosciences Union General Assembly",
    acronym: "EGU 2027",
    name: "EGU",
    theme: "ocean",
    also: ["uq"],
    found: "today",
    isNew: true,
    saved: false,
    byMylo: true,
    where: "Vienna, Austria",
    continent: "Europe",
    when: "Apr 4–9, 2027",
    eventIn: 148,
    month: "April",
    open: true,
    closesIn: 66,
    closesOn: "Jan 12",
    deadlines: [{ label: "Abstract", when: "Jan 12" }],
    reason: "A second venue for the reconstruction work with a strong uncertainty-in-ocean-models session.",
    caveat: "Travel budget would cover only one of OSM or EGU.",
    suggested: [
      { member: "ao", why: "Presenting the reconstruction." },
      { member: "pn", why: "Could co-present the calibrated version." },
    ],
    projects: ["Gulf SSH reconstruction"],
    source: "egu.eu",
  },
];

export const FEEDS: Record<FeedKind, FeedItem[]> = {
  paper: PAPERS,
  grant: GRANTS,
  fellowship: FELLOWSHIPS,
  conference: CONFERENCES,
};

export const FOUND = [
  { key: "papers", label: "papers", today: 12, week: 64 },
  { key: "grants", label: "grants", today: 3, week: 11 },
  { key: "fellowships", label: "fellowships", today: 2, week: 4 },
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

export function memberOf(id: string): Member {
  return MEMBERS.find((m) => m.id === id) ?? MEMBERS[0];
}

/** What Mylo is unsure of and asks rather than assumes ("Mylo & you"). */
export const MYLO_ASKS = [
  {
    id: "a1",
    question: "Is the triage-agent pilot still being written up?",
    context: "Two papers this week cite the same audit, and the project has had no edits in 12 days.",
    answers: ["Still writing", "Submitted"],
  },
  {
    id: "a2",
    question: "Should I watch “SWOT validation” for Ama?",
    context: "It came up in 4 of her saved papers but is not one of her topics.",
    answers: ["Watch it", "Not now"],
  },
];

export const KIND_LABEL: Record<FeedKind, string> = {
  paper: "Paper",
  grant: "Grant",
  fellowship: "Fellowship",
  conference: "Conference",
};

export function allItems(): FeedItem[] {
  return [...PAPERS, ...GRANTS, ...FELLOWSHIPS, ...CONFERENCES];
}
