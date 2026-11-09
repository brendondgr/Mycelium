# Mycelium Style Guide

Mycelium should feel like a warm, intelligent research workspace hidden inside a living forest network. The product blends research productivity, AI intelligence, organic mycelium networks, friendly mascot guidance, and soft SaaS dashboard design.

The core balance is important: Mycelium should be imaginative and memorable, but still mature enough for researchers, labs, faculty, and institutional partners to take seriously.

## Visual Direction

Use these words as design anchors:

- Organic
- Scholarly
- Warm
- Botanical
- Soft-tech
- Research-focused
- Trustworthy
- Friendly
- Living network

Avoid visual choices that feel overly childish, too fantasy-driven, too corporate, neon AI, generic SaaS blue, or crowded with illustration.

The design metaphor is a research dashboard mixed with a botanical field guide and an AI assistant platform. The interface should carry the serious work. Mylo should provide personality.

## Brand Feel

The visual identity is warm botanical SaaS. Use cream backgrounds, forest and moss greens, sage accents, mushroom beige, soft brown, and restrained gold. The design should feel calm, alive, and readable rather than sterile or flashy.

The dark theme should not be pure black or generic dark-dashboard blue. It should feel like a deep forest at night with a softly glowing research network.

Gold should be used sparingly. It represents valuable signals: grants, fellowships, deadlines, important findings, and opportunity alerts.

## Color Palette

Light theme:

| Role | Color | Use |
| --- | --- | --- |
| Background | `#F8F4EC` | Main page background |
| Surface | `#FFFDF8` | Cards, modals, panels |
| Surface Alt | `#EFE7D7` | Secondary panels and sidebars |
| Primary | `#5E7A3E` | Primary actions and brand states |
| Primary Hover | `#4D6733` | Hover and pressed states |
| Secondary | `#8DA66F` | Icons, tabs, subtle highlights |
| Accent | `#C9A35A` | Opportunities and important signals |
| Accent Soft | `#E7D8B8` | Alert backgrounds and soft badges |
| Text Primary | `#2E3627` | Main text |
| Text Secondary | `#5F6853` | Supporting text |
| Text Muted | `#7F8775` | Helper text and placeholders |
| Border | `#D9D0BE` | Cards and inputs |
| Divider | `#E8E0D1` | Separators |

Dark theme:

| Role | Color | Use |
| --- | --- | --- |
| Background | `#161B14` | Main app background |
| Surface | `#1D241A` | Cards and panels |
| Surface Alt | `#253021` | Raised UI blocks |
| Primary | `#8DA66F` | Primary actions |
| Primary Hover | `#A0B77F` | Hover and pressed states |
| Secondary | `#6F8A56` | Supporting UI elements |
| Accent | `#D3AE66` | Opportunities and important signals |
| Accent Soft | `#5B4A2A` | Dark accent surfaces |
| Text Primary | `#F2EBDD` | Main text |
| Text Secondary | `#C9C1B2` | Supporting text |
| Text Muted | `#9E988B` | Helper text and placeholders |
| Border | `#394431` | Cards and inputs |
| Divider | `#2B3427` | Separators |
| Focus | `#B8D99A` | Focus rings and subtle glow |

## Typography

Use a dual-type system:

- Headings should feel scholarly, organic, field-guide-like, and premium. Fraunces is the preferred direction; Lora, Cormorant Garamond, Playfair Display, or Libre Baskerville can also fit.
- UI and body text should be clean, readable, and functional. Inter or Manrope are the preferred directions; DM Sans, Geist, or Nunito Sans can also work.

Use large serif type for major marketing moments and important section headings. Use the sans-serif for navigation, buttons, dashboards, forms, labels, reports, and dense app surfaces.

## Mylo

Mylo is the mushroom scout and agent of the product. He searches, connects, alerts, and guides. He should be a functional part of the interface, not just decoration.

Use Mylo in places where the system is acting like a guide:

- Hero and brand moments
- Onboarding prompts
- Empty states
- Loading states
- Research discovery moments
- Grant or fellowship alerts
- Knowledge graph updates
- Success and error states

Mylo should stay cute but not childish. Keep expressions curious, observant, gentle, and helpful. Avoid making him overly goofy or placing him in every card.

Preferred Mylo direction:

> A small mushroom scout with a soft spore-like body, mushroom-cap hood, curious eyes, a research satchel, and subtle glowing mycelium threads that connect papers, people, projects, grants, and ideas.

### Mylo's chat panel

Talking to Mylo happens in one side panel, opened from anywhere: the launcher
(Mylo's painted head, fixed at the bottom right of every signed-in page,
hidden while the panel is open) or a Mylo-face button on a thing. At 980 px
and wider the panel lies over the reading pane and the page stays usable;
below that it is a full-screen sheet. Its header holds the title (renamable),
an "About" line for a conversation about one thing, and three icons — history,
new chat, pin — plus close.

**Mylo shows what he is doing, never what he is thinking.** Each turn has one
fold under the question: while Mylo works its header names the current step
with a quiet shimmer ("Searching the corpus for …"), opened it lists the steps
with a tick or a cross, and when the answer arrives it reads "Looked at 3
things". The words are the server's labels; the panel has none of its own.
Citations in an answer are small numbered pills that open the item. One line
under the composer names the model and whether it runs on this machine. Mylo's
head beside the fold floats gently while he works (Motion: Full only) and
stays still under reduced motion.

**"Ask Mylo" is a small button with Mylo's face** on each thing: first among a
feed card's tools and the opened item's, and beside the title of a project, a
lab overview and a department's overview. It is a real button and must never be
mistaken for the decorative portrait beside "Mylo's reason": the painted head
sits in a primary-green ring, it has the same 30 px target as its neighbours, a
visible focus ring, "Ask Mylo about <title>" as its name and "Ask Mylo" as its
tooltip, and it stays at full strength while the card's other tools fade. It
opens the panel on the conversation about that thing (one per thing) without
changing the reader's selection, and it is not drawn for someone who may not
chat — the launcher says why, once.

## Layout And Components

Use spacious, structured layouts with clear hierarchy. The public site should be persuasive, warm, and content-forward. The authenticated app should be denser, calmer, and built for repeated research workflows.

Core UI language:

- Soft panels
- Rounded cards
- Pill buttons
- Thin borders
- Warm shadows
- Green circular icon containers
- Faint mycelium network lines
- Subtle gold opportunity states

Use mycelium and root-network motifs as low-opacity connective tissue: background lines, section dividers, graph previews, loading animation, and dashboard visual language. Do not let the motif compete with content.

Cards should be readable and soft. Avoid harsh black borders, pure white surfaces, heavy shadows, and excessive nested cards.

### How a recommendation states itself

**A percentage only when it is a measurement.** The original ban was on a
language model's guessed similarity rendered as a percent beside a real
embedding cosine, with nothing to tell the reader which was which. That ban
stands: no model-guessed number is ever shown as a percent.

**The feed card states the measured match.** Every card in the app's feeds
(papers, grants, fellowships, conferences) and its opened item carry, top-left,
the item's **embedding similarity** to the reader's (or the lab's) profile —
the `embedding_match` cosine the backend already serves — as a ring and a
figure. Hovering or focusing it opens a breakdown by theme. Each theme pill
under the card carries that theme's share: `per_cluster` is a fusion score that
runs past 1, so a theme's figure is the overall similarity scaled by how
strongly that theme pulled the item relative to the theme that pulled it most.
The breakdown says this in words. An item with no measured similarity shows no
figure at all — never a substitute.

**Every feed card has one skeleton**, whatever its kind: match and New on the
left, the tools (remind, save, not-for-me) on the right; the title, two lines at
most; one **source line** (the venue's short name, or the funder or award class
with the money, or a conference's acronym and place — never wrapped, cut with an
ellipsis, full text on hover); one **meta line** (authors and year, or the
deadline pill with the posting date, event dates or stage); Mylo's reason on one
line; then at most three colour-coded theme pills on one line, each with its
figure. The opened item keeps the same top row, then the primary link on its own
ruled row with the deadline picker at its right (a conference's rankings sit
level with its site link), then every theme, Mylo's take with the caveat, and
**About** straight after it.

**Position and verdict stay off the feed.** "3rd in Medical AI Agents" and the
four-point verdict — Read, Skim, File, Skip — appear in the report entry, the
printed PDF, the Discord digest and the briefing, surfaces that present one
ordered pass through a day. Position is always within its own theme, never
overall: scores from two themes are not comparable. Read is filled primary
green, Skim sage, File neutral surface; a Skip is never chipped. The app's feed
cards carry neither: a feed interleaves themes and scrolls indefinitely, so a
per-theme position down its left edge read as a column of unsorted numbers. The
API still serves `verdict`, `position` and `position_of`.

The caveat — the strongest reason the item might not be worth your time, never
empty — is in the opened item under "Why it might not", not on the card. The
public site's feed preview must follow the app, not the report.

**Gold is not used for verdicts.** It stays reserved for opportunity and deadline
signals, so a grant's closing date never competes visually with a relevance
judgement two centimetres from it.

Where a verdict *is* shown and Mylo made the judgement rather than the
deterministic scorer, his portrait rides the chip. That is the honest signal that
a human-readable judgement exists behind it — and its absence is equally honest,
because most readers are on a plan without model reasoning and their document is
quieter, not broken.

## Public Site Direction

The public site should explain what Mycelium does, who it serves, why it is different from generic AI tools, and what the outputs look like.

**The public site is dark — "Night Forest".** It runs on the dark-forest palette (`data-theme="dark"` on every public page): a deep night ground, mycelium threads that grow up from the bottom of the hero and carry slow pulses of light, drifting spores, and entrance animations as content arrives. It is the most animated surface Mycelium has, and it should still read as a professional research product — the glow stays sage and, sparingly, gold.

**Mylo on the public site is painted art only** (`web/art/Mylo/MyloHeadshot-e1.png`, `MyloScout.png`), animated as an image (fade, float, glow), and only where he is acting as a guide — the report header, Mylo's reasons. The vector rig in `web/art/Mylo/svg/` is not used anywhere.

**Mycelium is open source, and there is no pricing page.** Every conversion is one of two ways in: sign up on the hosted site for free with a sign-up code, or run it yourself. No plans, tiers, trials or prices appear on the public site.

The front page moves through:

- Sticky night-glass navigation
- Hero: the **Mycelium** wordmark first, then "While you sleep, Mylo reads the field." and the two ways in. No Mylo figure on the opening screen — the user removed it; the name and the network carry it
- The 06:00 report writing itself — the output before the pitch
- The four feeds, as tabs over the workspace's own cards
- Every recommendation shows its work — a spotlight that tours one card's parts in order (the item, its theme, its summary, why it fits, why it might not) and follows the reader's hover
- What it covers, as a numbered catalogue
- How it works, as one night from 22:00 to 06:00
- Two ways in: hosted with a sign-up code, or self-hosted
- Final call to action and footer

The dashboard preview should prove product value, not only look pretty. It should show research pulse, knowledge connections, opportunity alerts, project snapshots, and next actions.

## App Direction

The authenticated workspace should feel like a quiet research operations dashboard. It should prioritize scanning, comparison, review, and action.

App surfaces should support:

- Lab goals
- Research feeds
- Papers and claims
- Projects
- Members
- Grants
- Fellowships
- Reports
- Knowledge graph exploration
- Notifications and settings

Every app view should account for loading, empty, populated, error, permission denied, job running, and stale-data states.

**The workspace wears Night Forest too.** It defaults to the dark-forest palette on the front page's night ground (`#10140e`), with Daylight kept as the reader's alternative. The workspace's look was chosen in the `/labs` playground and is the reference for any workspace change:

- **Background:** a still contour map at about a third of full strength. It is fixed behind the scroll area and masked away from the centre band where text sits, never blank and never animated.
- **Density:** compact, comfortable (the default) or open. This is a reader setting that reaches every page through the `--d-*` variables, not a per-page choice.
- **Chrome:** the workspace switcher is a header dropdown, the section navigation is a left rail that collapses to icons, and settings are listed in the account menu.
- **Feeds:** one page that scrolls through the cards. On wide screens the opened item is pinned on the right, below the feed's controls, and scrolls on its own. Below that it opens as a drawer. Every feed has search, filter menus, sort and grouping by theme. The controls stay pinned at the top while the cards scroll: the search on its own line, then the result count on the left with the filters and sort aligned right.
- **Cards:** one skeleton for every kind, as described above: the measured match and tools, the title, the source line, the meta line, Mylo's reason on one line, and the theme pills with their figures. No position or verdict marks.
- **Loading:** a placeholder in the shape of the page, which cross-fades into the content. Spinners are not used for a page's first load.

## Voice And Copy

Mycelium should speak like a calm research assistant, not a toy and not a hype machine.

Use copy like:

- "I found 12 papers relevant to your lab goals."
- "This fellowship matches your profile and timeline."
- "Three new papers strengthen your current proposal angle."
- "Your knowledge graph has 18 new connections."

Avoid copy like:

- "Supercharge your lab with AI magic."
- "Amazing discoveries await."
- "Revolutionize everything instantly."

The voice should be confident, concise, source-aware, and useful. When uncertainty exists, name it clearly.

## Motion

Motion should be slow, soft, subtle, and purposeful. Good motion includes gentle Mylo movement, softly pulsing nodes, graph lines drawing in, feature bubbles fading in, and cards lifting slightly on hover.

Avoid fast motion, constant bouncing, distracting backgrounds, or animation that makes research work feel less serious. Respect reduced-motion preferences, and the workspace's own Motion setting (Full, Subtle, None), where None stops everything.

## Accessibility And Responsiveness

The design should work across desktop, tablet, and mobile. Do not force dense dashboard previews into narrow screens. Simplify responsibly.

Do not rely on color alone for scores, alerts, chart states, graph meaning, or opportunity fit. Use labels, icons, shape, text, and layout in addition to color.

The product should meet WCAG 2.2 AA expectations for contrast, semantics, keyboard navigation, focus behavior, forms, and dynamic content.

## Mistakes To Avoid

- Making Mylo or the interface too cute for a research-lab audience
- Using too much illustration where product evidence is needed
- Weak information hierarchy across many features
- Large blocks of undifferentiated text
- Generic AI imagery, neon gradients, or robotic visuals
- Blue corporate SaaS defaults
- Decorative graphs that do not explain research value
- Alerts without explanations
- Recommendations that hide uncertainty or eligibility limits
