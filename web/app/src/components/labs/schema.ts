/**
 * Mycelium Labs — the option schema.
 *
 * Every control in the Labs sidebar is declared here, once: the preview reads
 * the chosen values, the sidebar renders the controls from this list, and the
 * export turns the same list into the block a person copies back to Claude.
 * Adding an option is one entry here plus whatever the preview does with it.
 *
 * Option ids are stable on purpose — the exported block quotes them
 * (`density=compact`), so an implementer can map a preference straight to the
 * code path that honours it.
 */

export type Choice = { value: string; label: string; hint?: string };

export type OptionDef =
  | {
      kind: "choice";
      id: string;
      label: string;
      help?: string;
      choices: Choice[];
      default: string;
    }
  | {
      kind: "toggle";
      id: string;
      label: string;
      help?: string;
      default: boolean;
    }
  | {
      kind: "range";
      id: string;
      label: string;
      help?: string;
      min: number;
      max: number;
      step: number;
      unit?: string;
      default: number;
    }
  | {
      kind: "multi";
      id: string;
      label: string;
      help?: string;
      choices: Choice[];
      default: string[];
    };

export type OptionValue = string | boolean | number | string[];

export type PageKey = "overview" | FeedKey | "search";

export type FeedKey = "papers" | "grants" | "fellowships" | "conferences";

export type PageDef = {
  key: PageKey;
  label: string;
  /** Where the real page lives today, quoted in the export. */
  route: string;
  options: OptionDef[];
};

/** The judgement a page can be given as a whole. Unset until someone picks. */
export const VERDICTS: Choice[] = [
  { value: "keep", label: "Ship this" },
  { value: "tweak", label: "Close — tweak" },
  { value: "rework", label: "Rework" },
];

export const GLOBAL_OPTIONS: OptionDef[] = [
  {
    kind: "choice",
    id: "theme",
    label: "Theme",
    choices: [
      { value: "night", label: "Night Forest", hint: "The front page's dark palette" },
      { value: "day", label: "Daylight", hint: "Cream and moss, the current app" },
    ],
    default: "night",
  },
  {
    kind: "choice",
    id: "background",
    label: "Background",
    help: "What sits behind the content instead of one flat colour.",
    choices: [
      { value: "plain", label: "Plain", hint: "One flat ground (today)" },
      { value: "threads", label: "Threads", hint: "Mycelium rising from the bottom edge, like the hero" },
      { value: "glow", label: "Glow", hint: "Soft pools of light at the edges" },
      { value: "spores", label: "Spores", hint: "Slow drifting specks" },
      { value: "contour", label: "Contour", hint: "Faint field-map lines" },
    ],
    default: "contour",
  },
  {
    kind: "range",
    id: "backgroundStrength",
    label: "Background strength",
    min: 0,
    max: 100,
    step: 5,
    unit: "%",
    default: 35,
  },
  {
    kind: "choice",
    id: "density",
    label: "Density",
    help: "Affects spacing, type size and how much each item shows.",
    choices: [
      { value: "compact", label: "Compact" },
      { value: "comfortable", label: "Comfortable" },
      { value: "open", label: "Open" },
    ],
    default: "comfortable",
  },
  {
    kind: "choice",
    id: "nav",
    label: "Navigation",
    choices: [
      { value: "rail", label: "Side rail", hint: "Collapses to icons; a drawer on phones" },
      { value: "tabs", label: "Header tabs", hint: "Sections across the top bar" },
      { value: "drawer", label: "Menu only", hint: "Everything behind one menu button" },
    ],
    default: "rail",
  },
  {
    kind: "toggle",
    id: "railCollapsed",
    label: "Side rail starts collapsed",
    default: true,
  },
  {
    kind: "choice",
    id: "scopeSwitcher",
    label: "Lab / department switcher",
    choices: [
      { value: "dropdown", label: "Header dropdown", hint: "“Pulse Lab ▾” beside the wordmark" },
      { value: "rail", label: "Left workspace rail", hint: "The current column of avatars" },
    ],
    default: "dropdown",
  },
  {
    kind: "choice",
    id: "surfaces",
    label: "Item style",
    help: "How a paper, grant or panel is drawn.",
    choices: [
      { value: "rows", label: "Rows", hint: "Hairline-separated, no boxes" },
      { value: "cards", label: "Soft cards", hint: "Filled panels, thin border" },
      { value: "glass", label: "Night glass", hint: "Translucent panels, like the front page" },
    ],
    default: "cards",
  },
  {
    kind: "choice",
    id: "radius",
    label: "Corners",
    choices: [
      { value: "tight", label: "Tight" },
      { value: "soft", label: "Soft" },
      { value: "round", label: "Round" },
    ],
    default: "soft",
  },
  {
    kind: "choice",
    id: "headings",
    label: "Headings",
    choices: [
      { value: "serif", label: "Fraunces serif", hint: "As on the front page" },
      { value: "sans", label: "Inter throughout" },
    ],
    default: "serif",
  },
  {
    kind: "choice",
    id: "width",
    label: "Content width",
    choices: [
      { value: "focused", label: "Focused" },
      { value: "wide", label: "Wide" },
      { value: "full", label: "Full" },
    ],
    default: "wide",
  },
  {
    kind: "choice",
    id: "detail",
    label: "Opening an item",
    choices: [
      { value: "drawer", label: "Side drawer", hint: "Slides in from the right; list stays put" },
      { value: "inline", label: "Expand in place" },
      { value: "modal", label: "Centered dialog" },
    ],
    default: "drawer",
  },
  {
    kind: "choice",
    id: "motion",
    label: "Motion",
    choices: [
      { value: "full", label: "Full", hint: "Entrances, pulses along threads" },
      { value: "subtle", label: "Subtle", hint: "Fades only" },
      { value: "none", label: "None" },
    ],
    default: "full",
  },
];

/**
 * The four feeds share one page design — a searchable, filterable list on the
 * left, the opened item on the right — so they share one set of options. The
 * few that only make sense for one kind (a board of grant statuses, grouping
 * papers by the day they were found) are added per kind.
 */
function feedPage(
  key: FeedKey,
  label: string,
  route: string,
  noun: "paper" | "grant" | "fellowship" | "conference",
): PageDef {
  const layouts: Choice[] = [
    { value: "reader", label: "List + reading pane", hint: "Opens on the right; a drawer on phones" },
    { value: "list", label: "List", hint: "Opens the way “Opening an item” says" },
    { value: "grid", label: "Two-up cards" },
  ];
  if (key === "grants") layouts.push({ value: "board", label: "Board", hint: "New · Closing soon · Saved" });

  const groups: Choice[] = [
    { value: "theme", label: "Theme" },
    { value: "none", label: "Nothing" },
  ];
  if (key === "papers") groups.push({ value: "day", label: "Day found" });
  else groups.push({ value: "month", label: key === "conferences" ? "Event month" : "Closing month" });

  const options: OptionDef[] = [
    { kind: "choice", id: "layout", label: "Layout", choices: layouts, default: "reader" },
    {
      kind: "choice",
      id: "filters",
      label: "Search & filters",
      help: "Every feed gets a search box; this is where the filters live.",
      choices: [
        { value: "bar", label: "Filter bar", hint: "A dropdown per filter, active ones as chips" },
        { value: "rail", label: "Filter column", hint: "Always open on the left (wide screens)" },
        { value: "drawer", label: "Behind a button", hint: "One “Filters” sheet" },
      ],
      default: "bar",
    },
    { kind: "choice", id: "groupBy", label: "Group by", choices: groups, default: "theme" },
    {
      kind: "multi",
      id: "card",
      label: "Each card shows",
      choices: [
        { value: "reason", label: "Mylo's reason" },
        { value: "caveat", label: "Why it might not fit" },
        { value: "who", label: "Who it's best for" },
        { value: "facts", label: noun === "paper" ? "Venue and authors" : "Amount, checks and dates" },
        { value: "themes", label: "Theme badges" },
      ],
      default: ["reason", "caveat", "who", "facts", "themes"],
    },
  ];
  if (key !== "papers") {
    options.push({
      kind: "choice",
      id: "deadline",
      label: "Dates shown as",
      choices: [
        { value: "countdown", label: "Countdown" },
        { value: "date", label: "Date" },
        { value: "both", label: "Both" },
      ],
      default: "both",
    });
  }
  return { key, label, route, options };
}

export const PAGES: PageDef[] = [
  {
    key: "overview",
    label: "Overview",
    route: "/app/overview",
    options: [
      {
        kind: "choice",
        id: "layout",
        label: "Layout",
        choices: [
          { value: "briefing", label: "Briefing", hint: "One reading column, top to bottom" },
          { value: "split", label: "Main + side", hint: "Today's items, with deadlines beside them" },
          { value: "bento", label: "Tiles", hint: "A grid of equal-weight panels" },
        ],
        default: "split",
      },
      {
        kind: "choice",
        id: "stats",
        label: "“What Mylo found” counts",
        choices: [
          { value: "strip", label: "One line", hint: "12 papers · 3 grants · …" },
          { value: "tiles", label: "Number tiles" },
          { value: "table", label: "Recency table", hint: "Today / week / month / year (today)" },
        ],
        default: "table",
      },
      {
        kind: "multi",
        id: "sections",
        label: "Sections shown",
        choices: [
          { value: "note", label: "Mylo's note" },
          { value: "today", label: "Today, by theme" },
          { value: "closing", label: "Closing soon" },
          { value: "found", label: "What Mylo found" },
          { value: "projects", label: "Project pulse" },
        ],
        default: ["note", "today", "closing", "found"],
      },
      {
        kind: "choice",
        id: "perTheme",
        label: "Items per theme",
        choices: [
          { value: "2", label: "2" },
          { value: "3", label: "3" },
          { value: "5", label: "5" },
        ],
        default: "3",
      },
    ],
  },
  feedPage("papers", "Papers", "/app/research-papers", "paper"),
  feedPage("grants", "Grants", "/app/grants", "grant"),
  feedPage("fellowships", "Fellowships", "/app/fellowships", "fellowship"),
  feedPage("conferences", "Conferences", "/app/conferences", "conference"),
  {
    key: "search",
    label: "Search",
    route: "/app/search",
    options: [
      {
        kind: "choice",
        id: "entry",
        label: "Search entry",
        choices: [
          { value: "centered", label: "Centered", hint: "Large, like a front door" },
          { value: "bar", label: "Compact bar" },
        ],
        default: "centered",
      },
      {
        kind: "choice",
        id: "frame",
        label: "Search box decoration",
        choices: [
          { value: "none", label: "None" },
          { value: "glow", label: "Soft glow on focus" },
          { value: "threads", label: "Threads under the box" },
          { value: "vine", label: "Vine around it", hint: "Today's version, for comparison" },
        ],
        default: "none",
      },
      {
        kind: "choice",
        id: "results",
        label: "Results",
        choices: [
          { value: "grouped", label: "Grouped by kind" },
          { value: "mixed", label: "One ranked list" },
        ],
        default: "grouped",
      },
      { kind: "toggle", id: "suggestions", label: "Suggest queries from my themes", default: true },
    ],
  },
];

export type LabsState = {
  page: PageKey;
  global: Record<string, OptionValue>;
  pages: Record<PageKey, Record<string, OptionValue>>;
  verdicts: Partial<Record<PageKey, string>>;
  notes: { global: string } & Partial<Record<PageKey, string>>;
};

function defaultsOf(options: OptionDef[]): Record<string, OptionValue> {
  return Object.fromEntries(options.map((o) => [o.id, o.default]));
}

export function defaultState(): LabsState {
  return {
    page: "overview",
    global: defaultsOf(GLOBAL_OPTIONS),
    pages: Object.fromEntries(
      PAGES.map((p) => [p.key, defaultsOf(p.options)]),
    ) as LabsState["pages"],
    verdicts: {},
    notes: { global: "" },
  };
}

/**
 * Lay a stored state over today's defaults, so an option added after the
 * browser saved its state still gets a value and a removed one is dropped.
 */
export function mergeState(stored: Partial<LabsState> | null): LabsState {
  const base = defaultState();
  if (!stored || typeof stored !== "object") return base;
  const pick = (opts: OptionDef[], from: Record<string, OptionValue> | undefined) =>
    Object.fromEntries(
      opts.map((o) => {
        const v = from?.[o.id];
        return [o.id, isValid(o, v) ? v : o.default];
      }),
    );
  return {
    page: PAGES.some((p) => p.key === stored.page) ? (stored.page as PageKey) : base.page,
    global: pick(GLOBAL_OPTIONS, stored.global),
    pages: Object.fromEntries(
      PAGES.map((p) => [p.key, pick(p.options, stored.pages?.[p.key])]),
    ) as LabsState["pages"],
    verdicts: { ...(stored.verdicts ?? {}) },
    notes: { global: "", ...(stored.notes ?? {}) },
  };
}

function isValid(o: OptionDef, v: unknown): v is OptionValue {
  switch (o.kind) {
    case "choice":
      return typeof v === "string" && o.choices.some((c) => c.value === v);
    case "toggle":
      return typeof v === "boolean";
    case "range":
      return typeof v === "number" && v >= o.min && v <= o.max;
    case "multi":
      return Array.isArray(v) && v.every((x) => o.choices.some((c) => c.value === x));
  }
}

function sameValue(a: OptionValue, b: OptionValue): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x) => b.includes(x));
  }
  return a === b;
}

function describe(o: OptionDef, v: OptionValue): string {
  switch (o.kind) {
    case "choice":
      return o.choices.find((c) => c.value === v)?.label ?? String(v);
    case "toggle":
      return v ? "On" : "Off";
    case "range":
      return `${v}${o.unit ?? ""}`;
    case "multi": {
      const list = ((v as string[] | undefined) ?? [])
        .map((x) => o.choices.find((c) => c.value === x)?.label ?? x)
        .join(", ");
      return list || "None";
    }
  }
}

function raw(v: OptionValue | undefined): string {
  return Array.isArray(v) ? v.join("+") || "none" : String(v);
}

function optionLines(options: OptionDef[], values: Record<string, OptionValue>): string[] {
  return options.map((o) => {
    const v = values[o.id];
    const changed = !sameValue(v, o.default);
    const mark = changed ? ` — changed (default: ${describe(o, o.default)})` : "";
    return `- ${o.label}: **${describe(o, v)}** \`${o.id}=${raw(v)}\`${mark}`;
  });
}

export function changedCount(state: LabsState): number {
  let n = 0;
  for (const o of GLOBAL_OPTIONS) if (!sameValue(state.global[o.id], o.default)) n++;
  for (const p of PAGES)
    for (const o of p.options) if (!sameValue(state.pages[p.key][o.id], o.default)) n++;
  return n;
}

function quote(text: string): string[] {
  return text
    .trim()
    .split("\n")
    .map((line) => `> ${line}`);
}

/**
 * The block a person pastes back to Claude. Markdown so it reads as a brief,
 * with every value also quoted as `id=value` so it maps back to this schema.
 */
export function buildExport(state: LabsState, today: string): string {
  const out: string[] = [
    "## Mycelium Labs — workspace design preferences",
    "",
    `Captured ${today} from \`/labs\`. Option ids are defined in \`web/app/src/components/labs/schema.ts\`; the preview that shows each one lives beside it in \`components/labs/preview/\`. Apply these to the authenticated workspace (\`web/app/src/components/portal/\`).`,
    "",
    "### Everywhere",
    ...optionLines(GLOBAL_OPTIONS, state.global),
  ];
  if (state.notes.global.trim()) out.push("", "Notes:", ...quote(state.notes.global));

  for (const p of PAGES) {
    out.push("", `### ${p.label} (\`${p.route}\`)`);
    const verdict = state.verdicts[p.key];
    out.push(
      `- Verdict: **${VERDICTS.find((v) => v.value === verdict)?.label ?? "Not judged"}**`,
    );
    out.push(...optionLines(p.options, state.pages[p.key]));
    const note = state.notes[p.key];
    if (note?.trim()) out.push("", "Notes:", ...quote(note));
  }
  return out.join("\n") + "\n";
}
