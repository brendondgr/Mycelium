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
  /** A live section that could be dropped: offers "Leave out", with this pitch. */
  optional?: string;
  variants: readonly LabVariant[];
};

const current = (pitch: string): LabVariant => ({ id: "current", name: "Live", pitch });

export const labSlots: readonly LabSlot[] = [
  {
    id: "hero",
    title: "Hero",
    status: "live",
    variants: [current("The wordmark over three planes of threads rooted at the bottom edge; the planes separate as you scroll away.")],
  },
  {
    id: "report",
    title: "The 06:00 report",
    status: "live",
    variants: [current("The sample report writes itself line by line as it scrolls into view.")],
  },
  {
    id: "feeds",
    title: "Four feeds",
    status: "live",
    variants: [current("One card from each feed, a tilted deck that deals itself into a spread once it is on screen.")],
  },
  {
    id: "work",
    title: "Shows its work",
    status: "live",
    variants: [current("The whole card, held in the middle of the screen beside its notes; a spotlight tours its parts.")],
  },
  {
    id: "mylo",
    title: "Ask Mylo",
    status: "live",
    variants: [current("One question asked in the app and in a Discord thread, answered by the same Mylo from the same sources.")],
  },
  {
    id: "announce",
    title: "Announcements in Discord",
    status: "live",
    variants: [current("New calls as threads in the lab's Discord forums, with Interested, Remind me, Not for us and View the call.")],
  },
  {
    id: "covers",
    title: "What it covers",
    status: "live",
    variants: [current("Every capability as a node on one map; hovering a node lights what it connects to.")],
  },
  {
    id: "night",
    title: "How it works",
    status: "live",
    variants: [current("One night on a clock, 22:00 to 06:00 left to right; it plays once on arrival and each stop puts up its card.")],
  },
  {
    id: "stack",
    title: "The grounding layer",
    status: "live",
    variants: [current("Mycelium as stacked layers (corpus, profiles, graph, feeds) with the tools on top; the plates separate as you scroll.")],
  },
  {
    id: "ways",
    title: "Ways in",
    status: "live",
    variants: [current("Two ways in: hosted with a sign-up code, or self-hosted with make setup.")],
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
 * the lab so the content decisions are made alongside the visual ones. An
 * empty list is not shown.
 */
export const labAudit: { stale: readonly { where: string; issue: string }[]; missing: readonly string[] } = {
  stale: [],
  missing: [
    "Deployment profiles by name (personal, lab, department, institution): Ways in says make setup asks who the instance is for, but not the choices",
  ],
};
