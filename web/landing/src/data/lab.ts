/**
 * The front page lab (`/lab`): every section of the front page, in order, with
 * the prototypes that could replace it and the new sections that could join it.
 *
 * Not part of the public site. It is a page for deciding: it renders the real
 * front page with a switcher on each section, so a prototype is judged in
 * place, against its neighbours and with the real scroll effects, rather than
 * on its own. The panel collects a pick and a note per section and copies the
 * lot as Markdown for the next session to build from.
 *
 * Adding a prototype: write the component under `components/lab/<slot>/`, add
 * its entry here, and map `<slot>/<id>` to it in `pages/lab.astro`. The
 * contract every prototype keeps is written at the top of that page.
 */

export type LabVariant = {
  /** `current` is the live front-page section. */
  id: string;
  /** Short name on the switcher. */
  name: string;
  /** One sentence: what this version is. */
  pitch: string;
  /** What the version says that the live page does not (or corrects). */
  content?: readonly string[];
  /** How it adds depth or motion. */
  depth?: readonly string[];
};

export type LabSlot = {
  id: string;
  title: string;
  /** `live` sections are on the front page now; `new` ones are proposals. */
  status: "live" | "new";
  variants: readonly LabVariant[];
};

const current = (pitch: string): LabVariant => ({ id: "current", name: "Live", pitch });

export const labSlots: readonly LabSlot[] = [
  {
    id: "hero",
    title: "Hero",
    status: "live",
    variants: [
      current("The wordmark over threads that grow up from the bottom edge, with pulses and drifting spores."),
      {
        id: "depth-field",
        name: "Depth field",
        pitch: "The same threads split into three planes (far, middle, near) that drift apart as you scroll and lean with the pointer, and the copy sinks back into the night.",
        depth: [
          "Three thread planes with their own blur, brightness and scroll rate",
          "Spores sized and blurred by plane, so near ones read as close",
          "The copy scales back and fades as the near plane rises past it",
        ],
      },
      {
        id: "constellation",
        name: "Constellation",
        pitch: "The threads end in labelled nodes (a paper, a call, a person, a project) that light up in turn, so the opening shows what the network connects.",
        content: [
          "Names the four feeds and the lab's own people and projects in the first screen",
        ],
        depth: [
          "Nodes light in sequence along the thread that reaches them",
          "A faint second network sits behind, out of focus",
        ],
      },
    ],
  },
  {
    id: "report",
    title: "The 06:00 report",
    status: "live",
    variants: [
      current("The sample report writes itself line by line as it scrolls into view."),
      {
        id: "fanned",
        name: "Three deliveries",
        pitch: "The report as a stack of its three deliveries (the app, the PDF, the lab's Discord channel) that fans apart in perspective as you scroll.",
        content: [
          "Shows that the same report reaches the app, a PDF and Discord",
          "The Discord copy leads with the counts-by-theme summary, as the real post does",
        ],
        depth: [
          "Three sheets in 3D perspective that separate with the scroll",
          "Each sheet casts a warm shadow on the one beneath",
        ],
      },
      {
        id: "scrubbed",
        name: "Annotated",
        pitch: "The section pins while you scroll and the report writes in step with the scroll, with margin notes pointing at the theme position, the verdict, the caveat and the deadline.",
        content: [
          "Explains where a position comes from (within its theme, never overall) and the four verdicts",
        ],
        depth: [
          "A pinned stage scrubbed by the scroll, forwards and backwards",
          "Margin notes draw a hairline to the line they explain",
          "A 22:00 to 06:00 bar fills as the report writes",
        ],
      },
    ],
  },
  {
    id: "feeds",
    title: "Four feeds",
    status: "live",
    variants: [
      current("The four feeds as tabs over the workspace's own cards."),
      {
        id: "deck",
        name: "Fanned deck",
        pitch: "One card from each feed, stacked as a tilted deck that fans out into a spread as you scroll; hover or focus lifts a card to the front.",
        depth: [
          "Cards stacked in perspective, separated in depth as well as position",
          "The front card is sharp; cards behind are dimmed and slightly blurred",
        ],
      },
    ],
  },
  {
    id: "work",
    title: "Shows its work",
    status: "live",
    variants: [
      current("The whole card beside its notes; a spotlight tours its parts and follows the reader's hover."),
      {
        id: "exploded",
        name: "Exploded view",
        pitch: "The card comes apart in layers (match, item, reason, themes, tools) that lift off in depth as you scroll, each labelled, then settle back into one card.",
        depth: [
          "An isometric stack: each part on its own plane with its own shadow",
          "Pinned while it explodes and re-assembles, so the reader controls it",
        ],
      },
    ],
  },
  {
    id: "mylo",
    title: "Ask Mylo",
    status: "new",
    variants: [
      {
        id: "panel",
        name: "Chat panel",
        pitch: "A sample conversation plays out in Mylo's side panel: the fold names each step as he works, ticks them off, and the answer arrives with citation pills.",
        content: [
          "Mylo now answers questions, from everything the person is allowed to see",
          "He shows what he is doing, never what he is thinking",
          "Read-only: he looks things up, he does not change anything",
          "Available from any card, project or lab with \"Ask Mylo\"",
        ],
        depth: [
          "The panel floats over a dimmed slice of the workspace behind it",
          "Steps shimmer while running and settle when done",
        ],
      },
      {
        id: "two-places",
        name: "Web and Discord",
        pitch: "One question asked in two places, the web panel and a Discord thread, answered by the same Mylo with the same sources.",
        content: [
          "Mylo answers a DM, an @mention or a reply in Discord through the same agent",
          "A thread is one shared conversation, each question answered under its asker",
        ],
        depth: [
          "The two surfaces sit on separate planes and slide together on scroll",
          "A thread of light carries the question from one to the other",
        ],
      },
    ],
  },
  {
    id: "announce",
    title: "Announcements in Discord",
    status: "new",
    variants: [
      {
        id: "forum",
        name: "Forum threads",
        pitch: "New calls arrive as threads in the lab's Discord forums, one per call, with Interested, Remind me, Not for us and View the call on each.",
        content: [
          "Each call becomes its own thread, and a changed call updates its thread rather than posting again",
          "Who should look: the project teams it suits, by name",
          "Anyone in the server can set a reminder, with no Mycelium account",
          "Conference threads lead with the place and are tagged by continent",
        ],
        depth: [
          "Threads slide in from depth, newest in front",
          "The buttons press in with a soft shadow",
        ],
      },
      {
        id: "checks",
        name: "Can we use this?",
        pitch: "One call, checked line by line as it scrolls in: open or closed, the next deadline against the lab's buffer, who may apply and from where, and whether the department hears first.",
        content: [
          "Every opportunity carries checks read from the call itself",
          "Departments hear about calls a lab cannot take on alone (limited submissions, nominations)",
          "What Mylo held back, and why, stays visible on the lab overview",
        ],
        depth: [
          "Each check ticks in on its own beat",
          "Failed checks stay in place, named, rather than being hidden",
        ],
      },
    ],
  },
  {
    id: "covers",
    title: "What it covers",
    status: "live",
    variants: [
      current("Six numbered entries with line drawings that draw themselves in."),
      {
        id: "network",
        name: "Living map",
        pitch: "The capabilities as nodes on one network that draws in with the scroll; hovering a node lights the things it connects to.",
        content: [
          "Adds conferences, projects, departments, Mylo chat and Discord to the list",
          "Shows the connections (a grant to a project, a fellowship to a person) rather than listing parts",
        ],
        depth: [
          "Nodes on three depths; the map tilts toward the pointer over a blurred far network",
          "Threads draw in on scroll; a hovered node's threads brighten and the rest dim",
        ],
      },
      {
        id: "catalogue",
        name: "Catalogue, corrected",
        pitch: "The same catalogue form, brought up to date: nine entries for what ships now, and no claim the code does not yet make good.",
        content: [
          "Drops \"contradictions\" from the knowledge entry: contradiction detection is not built",
          "Adds conferences with their rankings, projects, departments, Mylo chat and Discord announcements",
        ],
        depth: [
          "Entries rise from slightly different depths, so the grid reads as a field",
        ],
      },
    ],
  },
  {
    id: "night",
    title: "How it works",
    status: "live",
    variants: [
      current("One night from 22:00 to 06:00 down a line that grows with the scroll."),
      {
        id: "dawn",
        name: "Night to dawn",
        pitch: "The section pins and the sky turns from night to dawn as you scroll, with layered hills rising at different speeds and the steps lighting one at a time.",
        content: [
          "Says what the night actually does: rank the whole corpus again per theme, report only what entered, reuse every write-up it already paid for",
        ],
        depth: [
          "Three layers of hills in parallax under a sky that warms from night to gold",
          "A clock hand sweeps 22:00 to 06:00 with the scroll",
        ],
      },
    ],
  },
  {
    id: "stack",
    title: "The grounding layer",
    status: "new",
    variants: [
      {
        id: "layers",
        name: "Stacked layers",
        pitch: "Mycelium as layers: the corpus, the profiles, the graph and the feeds at the bottom, and the tools built on them on top. The layers separate on scroll to show what rests on what.",
        content: [
          "Introduces Mycelium as the grounding layer research tools are built on",
          "Tools are modular: each lives in its own folder with its own settings, and one that cannot load is set aside",
          "The language model is yours: any compatible endpoint, local or hosted",
        ],
        depth: [
          "An isometric stack of plates that separates with the scroll",
          "Threads run up through the plates, linking a tool to what it reads",
        ],
      },
    ],
  },
  {
    id: "ways",
    title: "Ways in",
    status: "live",
    variants: [
      current("Two ways in: hosted with a sign-up code, or self-hosted with three commands."),
      {
        id: "three-doors",
        name: "Three doors",
        pitch: "Hosted, demo and self-hosted side by side. The terminal runs make setup and asks who the instance is for: personal, lab, department or institution.",
        content: [
          "make setup replaces docker compose up (it writes the config and secrets, migrates, and creates the admin)",
          "Names the four deployment profiles (the terminal shows the profile question and skips the model-endpoint ones)",
          "Puts the demo lab in as its own door, shown only when the demo is on",
        ],
        depth: [
          "Doors at slightly different depths that open toward you on hover",
          "The terminal types its run as it arrives",
        ],
      },
    ],
  },
  {
    id: "cta",
    title: "Final call to action",
    status: "live",
    variants: [current("Plant your lab's profile tonight.")],
  },
];

/**
 * Where the live front page has fallen behind the product. Shown at the top of
 * the lab so the content decisions are made alongside the visual ones.
 */
export const labAudit = {
  stale: [
    {
      where: "What it covers · Knowledge connections",
      issue: "Says claims and contradictions are linked into an evidence graph. The graph exists (concepts and typed edges with an evidence tier), but claim modelling and contradiction detection are not built.",
    },
    {
      where: "How it works · 04:00",
      issue: "\"Papers, claims, methods and datasets link into a graph your team can review\" claims more of the graph than the app shows.",
    },
    {
      where: "Two ways in · Self-hosted",
      issue: "The commands end in docker compose up. A fresh clone is set up with make setup, which writes the config and secrets, migrates and creates the admin.",
    },
  ],
  missing: [
    "Mylo answers questions, in the web app and in Discord, and shows his steps",
    "Opportunity announcements as Discord forum threads with Interested, Remind me and Not for us",
    "Anyone in a lab's server can set a reminder, with no account",
    "\"Can we use this?\" checks on every opportunity",
    "Departments, and the calls only a department can take on",
    "Projects with their own state: what they claim, what blocks them, what they aim at",
    "Conference rankings (CORE, CCF) and submission deadlines rather than event dates",
    "Deployment profiles: personal, lab, department, institution",
    "Your own model: any compatible endpoint, and the page says when it is not on this machine",
  ],
} as const;
