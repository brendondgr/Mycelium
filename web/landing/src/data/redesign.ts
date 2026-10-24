/**
 * Content for the `/redesign` preview — a review page, not a public one.
 *
 * Three alternative front pages are rendered side by side on one URL so they
 * can be compared against the live `/`. Nothing here is linked from the site
 * and the page is `noindex`. Once a direction is chosen, the winning concept's
 * pieces move into `components/landing/` and this file, the page and
 * `components/redesign/` are deleted.
 */

export type ConceptId = "living" | "night" | "guide";

export type Concept = {
  id: ConceptId;
  letter: string;
  name: string;
  oneLine: string;
  /** What changes against the live page, in the order a reader meets it. */
  changes: readonly string[];
  /** Every moving thing in the concept — the motion budget, stated. */
  motion: readonly string[];
  /** What it would take to ship, and what could go wrong. */
  cost: string;
  risk: string;
};

export const concepts: readonly Concept[] = [
  {
    id: "living",
    letter: "A",
    name: "Living Network",
    oneLine:
      "Light, clean and product-forward. The hero becomes a live map of what Mylo found overnight, drawn from the real feed kinds.",
    changes: [
      "Floating pill navigation that tightens as you scroll (the style guide asks for floating; the live header is a full-width bar).",
      "Hero swaps the painted backdrop for the animated Mylo rig at the centre of a growing network — papers, grants, a fellowship, a conference and a contradiction branch out from him.",
      "The six identical feature cards become a bento grid where each tile shows its own evidence: a real paper card, a deadline ring, an eligibility checklist, a claim graph, an action list.",
      "How it works becomes a day cycle (evening → 02:00 → 04:00 → 06:00) with a spore travelling the track.",
      "Meet Mylo uses the rig again: he waves when the call to action is hovered or focused.",
    ],
    motion: [
      "Hyphae draw outward from Mylo on load, then each node sprouts and its label fades in",
      "Three spores travel the network on slow 9–13 s loops",
      "Mylo: search pose with the magnifier in the hero; wave on CTA hover",
      "Bento tiles: ring and checklist animate once on entry; cards lift on hover",
    ],
    cost:
      "Smallest change. Reuses the feed cards, tokens and reveal system; the new work is the hero network and the bento tiles.",
    risk:
      "The network carries sample labels — they must stay obviously illustrative, like the feed preview does today.",
  },
  {
    id: "night",
    letter: "B",
    name: "Night Forest",
    oneLine:
      "Dark and bioluminescent. Leans on the brand's 'deep forest at night with a softly glowing research network' — the product works while the lab sleeps.",
    changes: [
      "Whole page on the dark-forest palette, so it doubles as the design for a public dark mode.",
      "Hero: mycelium grows up from the bottom edge and pulses of light run along it; spores drift past the headline.",
      "A sample 06:00 report writes itself line by line, so the first thing proved is the output, not the promise.",
      "The four feeds become tabs over the real workspace cards, rendered in the dark theme.",
      "Trust becomes an exploded diagram of one card — item, theme, reason, caveat — and drops the '88% fit' the live trust band still shows.",
      "How it works is told as one night, 22:00 to 06:00.",
    ],
    motion: [
      "Threads grow from the ground on load (staggered over ~3 s), then light pulses travel them",
      "Spores rise and twinkle on 14–26 s loops",
      "Report lines arrive one by one with a caret when scrolled into view",
      "Anatomy callout lines draw toward their labels",
    ],
    cost:
      "Medium. Most of it is new composition; tokens already invert, and the feed cards render dark without changes.",
    risk:
      "A dark marketing site is a stronger brand bet. Gold and sage glow must stay restrained or it tips into 'neon AI', which the style guide rules out.",
  },
  {
    id: "guide",
    letter: "C",
    name: "Field Guide",
    oneLine:
      "Editorial and scholarly. The page reads like a botanical field guide for research — plates, numbered entries, marginal notes.",
    changes: [
      "Journal-masthead navigation with a centred wordmark and a double rule.",
      "Hero: oversized Fraunces with italics, beside a circular specimen plate of Mylo whose ring is labelled with the four feeds.",
      "Features become a numbered catalogue of entries with hairline rules instead of cards.",
      "One real paper card is annotated in the margins — the reason, the caveat that is never empty, the theme it matched.",
      "How it works is a circular daily cycle whose arc draws as you scroll.",
      "A single hypha grows down the left margin with your reading progress.",
    ],
    motion: [
      "Specimen ring turns once a minute; marginal leader lines draw in",
      "Margin hypha grows with scroll position (scroll-driven, no script)",
      "Cycle arc draws with scroll; stages light as it passes",
      "Mylo: think pose, slow",
    ],
    cost:
      "Medium. Mostly typography and layout; the scroll-driven pieces degrade to their finished state where unsupported.",
    risk:
      "Most distinctive, least 'SaaS'. Fits the scholarly audience but asks more of the copy — weak sentences show at this type size.",
  },
] as const;

/** What reads as dated on the live `/`, found by reading its code and render. */
export const audit = [
  {
    title: "The header is a bar, not floating",
    detail:
      "docs/styles.md opens the front page with floating navigation. The live header is a full-width sticky strip — the most 2018 thing on the page.",
  },
  {
    title: "The hero is a painting with text on it",
    detail:
      "Copy sits over a busy raster illustration, so the crop has to walk left at every breakpoint to keep Mylo out from under the headline. Nothing in the hero moves except the text fading in.",
  },
  {
    title: "The animated Mylo is unused",
    detail:
      "web/art/Mylo/svg/mylo.svg is a full rig — idle, walk, wave, search, write, cheer — and the public site shows only static PNG crops of him.",
  },
  {
    title: "Six identical feature cards",
    detail:
      "Icon bubble, bold title, two lines, repeated six times over a second painting. It is the generic SaaS grid the style guide warns against, and it proves nothing.",
  },
  {
    title: "Hardcoded colours bypass the theme",
    detail:
      "FeatureStrip uses literal hex (#f8f4ec, #1f2b1d, #3f6e34 …) instead of tokens, so it cannot follow a dark theme — and the public site has no dark theme at all.",
  },
  {
    title: "Every section has the same shape",
    detail:
      "Eyebrow, serif heading, paragraph, max-w-6xl, one 20 px fade-up. Eight times. The rhythm never changes, so nothing reads as the moment.",
  },
  {
    title: "The product proof is buried and very long",
    detail:
      "The live feed preview is the best evidence on the page and it is 1,850 px tall in third position.",
  },
  {
    title: "The trust band contradicts the style guide",
    detail:
      "It shows '88% fit'. docs/styles.md: a recommendation states itself never as a percentage. All three concepts drop it.",
  },
] as const;

export const recommendation =
  "Start from A — it is the safest step and fixes every audit item. Borrow B's hero and palette as the public dark mode, and C's annotated paper card for the trust section, where explaining one match beats asserting trust.";
