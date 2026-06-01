# Mycelium Website Style Breakdown

The website should feel like:

> **A warm, intelligent research workspace hidden inside a living forest network.**

The style should combine:

* **research productivity**
* **AI intelligence**
* **organic mycelium networks**
* **friendly mascot guidance**
* **soft SaaS dashboard design**

The important balance is this:

> It should feel imaginative and branded, but still clean enough that researchers, labs, and faculty take it seriously.

---

# 1. Core Visual Direction

## Style Keywords

Use these as design anchors:

```text
organic
scholarly
warm
botanical
soft-tech
research-focused
trustworthy
friendly
living network
```

Avoid:

```text
overly childish
too fantasy
too corporate
neon AI
generic SaaS blue
overcrowded illustration
```

The mascot gives the site personality, but the UI needs to stay structured and professional.

---

# 2. Overall Design Language

The website should use a **soft organic SaaS** style.

That means:

| Element       | Direction                               |
| ------------- | --------------------------------------- |
| Backgrounds   | warm cream, parchment, subtle gradients |
| Cards         | rounded, soft shadows, light borders    |
| Buttons       | pill-shaped, moss green                 |
| Icons         | simple line icons inside green circles  |
| Illustrations | flat vector Mylo, botanical accents     |
| Motifs        | mycelium/root network lines             |
| Typography    | large serif hero + clean sans UI        |
| Layout        | spacious, grid-based, not cluttered     |

The site should feel like a mix of:

```text
research dashboard + botanical field guide + AI assistant platform
```

---

# 3. Color System

Use the mascot colors directly.

## Light Theme

| Role          |     Color | Use                          |
| ------------- | --------: | ---------------------------- |
| Background    | `#F8F4EC` | main site background         |
| Surface       | `#FFFDF8` | cards, navbar, panels        |
| Surface Alt   | `#EFE7D7` | feature strips, side panels  |
| Primary Green | `#5E7A3E` | buttons, active states, logo |
| Deep Green    | `#3F5A2A` | headings, hover states       |
| Sage          | `#8DA66F` | icons, secondary accents     |
| Gold          | `#C9A35A` | highlights, alert details    |
| Text Primary  | `#2E3627` | main readable text           |
| Text Muted    | `#5F6853` | secondary copy               |
| Border        | `#D9D0BE` | card and input borders       |

## Dark Theme

| Role          |     Color | Use                       |
| ------------- | --------: | ------------------------- |
| Background    | `#161B14` | app background            |
| Surface       | `#1D241A` | cards                     |
| Surface Alt   | `#253021` | raised panels             |
| Primary       | `#8DA66F` | buttons and links         |
| Primary Hover | `#A0B77F` | hover                     |
| Accent Gold   | `#D3AE66` | opportunities, highlights |
| Text Primary  | `#F2EBDD` | main text                 |
| Text Muted    | `#C9C1B2` | secondary text            |
| Border        | `#394431` | borders                   |

Use gold sparingly. It should represent:

* grant alerts
* fellowship opportunities
* important signals
* “found something valuable”

---

# 4. Typography

Use a **dual-type system**.

## Headings

Use a warm serif or soft display font for major marketing text.

Good feel:

```text
scholarly
organic
field-guide-like
premium
```

Possible font styles:

* Fraunces
* Lora
* Cormorant Garamond
* Playfair Display
* Libre Baskerville

Use for:

* hero headline
* section headings
* large marketing statements

Example:

```text
Living Intelligence for Research Labs
```

## UI Text

Use a clean sans-serif for everything functional.

Possible fonts:

* Inter
* Manrope
* DM Sans
* Geist
* Nunito Sans

Use for:

* nav
* buttons
* dashboard cards
* feature descriptions
* forms
* labels

## Recommended Pairing

```text
Headings: Fraunces
UI/body: Inter or Manrope
```

That gives the site personality without losing readability.

---

# 5. Page Structure

The front page should be organized like this:

```text
Navbar
Hero Section
Feature Strip
Product Dashboard Preview
How It Works
Use Cases
Mascot / Mylo Section
Call to Action
Footer
```

The generated mockup already captures the first three sections well.

---

# 6. Navbar Design

The navbar should feel soft and floating.

## Structure

```text
[Logo + Mycelium]     Product     Solutions     Resources     Pricing     About      Log in    Get Started
```

## Style

* rounded full-width container
* cream/white background
* subtle border
* soft shadow
* sticky if desired
* max width around `1200px` or `1280px`
* centered horizontally

## Logo

Use:

```text
leaf / mycelium emblem + Mycelium
```

Subtext can be:

```text
AI for Research Labs
```

But only if it does not clutter the navbar.

For smaller screens, only show:

```text
icon + Mycelium
```

---

# 7. Hero Section

The hero should be the emotional center of the site.

## Layout

Use a two-column layout.

```text
Left: headline, description, CTAs
Right: Mylo illustration + floating feature bubbles
```

## Left Content

The headline should be large and memorable.

Examples:

```text
Living Intelligence for Research Labs
```

or

```text
Your Lab’s Research Scout
```

or

```text
Find, Connect, and Grow Research Ideas
```

Subheadline:

```text
Mycelium helps labs discover literature, connect knowledge, find grants and fellowships, and guide research strategy.
```

## CTA Buttons

Primary:

```text
Get Started
```

Secondary:

```text
Meet Mylo
```

or

```text
View Demo
```

Button style:

* primary: moss green fill
* secondary: cream fill, green/brown border
* rounded pill
* subtle shadow

---

# 8. Mylo Integration

Mylo should not be decoration only.

He should act like the **guide/agent** of the system.

## Best Uses

| Location       | Mylo Role                      |
| -------------- | ------------------------------ |
| Hero           | main research scout            |
| Empty states   | “No papers found yet”          |
| Alerts         | “I found a grant match”        |
| Dashboard      | small helper pose              |
| Onboarding     | asks lab profile questions     |
| Loading states | searching / connecting nodes   |
| Error states   | tangled in roots               |
| Success states | holding a found paper or badge |

## Recommended Mylo Poses

Use these throughout the site:

| Pose               | Use               |
| ------------------ | ----------------- |
| Magnifying glass   | literature search |
| Connecting nodes   | knowledge graph   |
| Bell/document      | grant alert       |
| Profile card       | fellowship match  |
| Pointer board      | research planning |
| Open hand/notebook | team guidance     |

This gives the mascot a functional design system.

---

# 9. Mycelium Network Motifs

The mycelium/root network should be a recurring visual pattern.

Use it as:

* faint background lines
* section dividers
* animated connection lines
* graph visualization motif
* hero background pattern
* loading animation
* dashboard visual language

Do not overuse it.

Best approach:

```text
Low opacity, thin lines, soft gold or sage dots
```

Example:

```css
opacity: 0.12;
stroke: #C9A35A;
```

The network motif should suggest:

```text
papers → claims → people → projects → grants
```

---

# 10. Feature Strip

The feature strip in the mockup is strong.

Use a horizontal rounded card with six feature blocks.

## Features

```text
Literature Search
Knowledge Graph
Grant Alerts
Fellowship Match
Research Planning
Team Guide
```

Each feature should have:

* circular icon
* title
* 1–2 sentence description
* small Mylo spot illustration if available

## Example Card

```text
Literature Search
Find the right papers faster with smart semantic search.
```

The feature strip should be visually lighter than the hero. It should summarize the product quickly.

---

# 11. Dashboard Preview

The dashboard preview should show the actual value of the product.

Do not make it decorative only.

## Dashboard Sections

Include cards like:

### Research Pulse

Shows:

* new papers
* trending topics
* relevance score
* “24 new papers”

### Knowledge Connections

Shows:

* mini graph
* connected claims
* related projects

### Opportunity Alerts

Shows:

* grants
* fellowships
* deadlines
* match score

### Project Snapshot

Shows:

* progress
* milestones
* missing documents
* next actions

This helps the viewer understand:

> “This is not just a cute AI mascot. This is a real research operations dashboard.”

---

# 12. Card Design

Cards should be soft, rounded, and readable.

## Card Style

```css
background: #FFFDF8;
border: 1px solid #D9D0BE;
border-radius: 24px;
box-shadow: 0 12px 30px rgba(46, 54, 39, 0.08);
padding: 24px;
```

## Card Rules

* no harsh black borders
* avoid pure white backgrounds
* use subtle beige shadows
* keep spacing generous
* use green icons
* use gold only for alerts/opportunities

---

# 13. Icon Style

Icons should match the mascot.

Use:

* rounded line icons
* green circular backgrounds
* simple shapes
* no sharp futuristic icons

Icon ideas:

| Feature           | Icon                     |
| ----------------- | ------------------------ |
| Literature Search | magnifying glass         |
| Knowledge Graph   | connected nodes          |
| Grant Alerts      | gift box, bell, document |
| Fellowship Match  | profile card + check     |
| Research Planning | compass, map, board      |
| Team Guide        | group/person icon        |
| Lab Profile       | leaf badge               |
| Deadlines         | calendar                 |
| Evidence          | document/checkmark       |
| Privacy           | lock/shield              |

Icon containers:

```css
background: #5E7A3E;
color: #FFFDF8;
border-radius: 999px;
```

---

# 14. Layout Rules

Use a clean grid.

## Desktop

```text
max-width: 1200px to 1280px
hero: 2 columns
features: 6-column or 3x2 grid
dashboard: large mockup card
sections: alternating text/image
```

## Tablet

```text
hero: stacked or 60/40
features: 3x2
dashboard: horizontally scrollable or simplified
```

## Mobile

```text
hero: text first, Mylo second
features: single column
dashboard: simplified cards
navbar: hamburger
```

Do not force the full dashboard preview onto mobile.

---

# 15. Section-by-Section Design

## Section 1: Hero

Goal:

> Explain product and build emotional identity.

Elements:

* badge: “Your AI Research Scout”
* headline
* subheadline
* CTA buttons
* trust chips
* large Mylo
* floating feature bubbles

---

## Section 2: Feature Strip

Goal:

> Show what the product does.

Elements:

* six feature cards
* small icons
* short labels
* small mascot spots

---

## Section 3: Dashboard Preview

Goal:

> Prove the product is useful.

Elements:

* fake app UI
* research pulse
* knowledge graph
* opportunity alerts
* project progress
* sidebar navigation

---

## Section 4: How It Works

Use a 4-step process.

```text
1. Build your lab profile
2. Connect papers, projects, and people
3. Monitor research and opportunities
4. Get personalized guidance
```

Use mycelium lines connecting the steps.

---

## Section 5: Use Cases

Separate audiences:

```text
For PIs
For PhD Students
For Research Teams
For Grant Writers
```

Example:

| Audience      | Value                                  |
| ------------- | -------------------------------------- |
| PIs           | lab strategy, grants, project tracking |
| Students      | fellowship matching, paper discovery   |
| Teams         | shared research memory                 |
| Grant writers | evidence tables and deadline tracking  |

---

## Section 6: Meet Mylo

This is where mascot branding becomes clear.

Example copy:

```text
Meet Mylo, your Mushroom Scout.
He searches the research forest, connects hidden ideas, and brings back papers, grants, fellowships, and strategy signals for your lab.
```

Show several Mylo poses.

---

## Section 7: CTA

Use a warm ending.

```text
Start growing your lab’s research intelligence.
```

Buttons:

```text
Get Started
View Demo
```

---

# 16. Animation Ideas

Use very subtle animation.

Good animations:

* Mylo gently floating or blinking
* mycelium nodes pulsing softly
* feature bubbles fading in
* graph lines drawing themselves
* cards lifting slightly on hover
* grant alert badge glowing softly

Avoid:

* fast motion
* bouncing everywhere
* cartoonish excessive animation
* distracting background movement

Animation speed:

```text
slow
soft
subtle
organic
```

---

# 17. UI Personality

The UI should speak like a research assistant, not a toy.

## Good Copy

```text
I found 12 papers relevant to your lab goals.
```

```text
This fellowship matches your profile and timeline.
```

```text
Three new papers strengthen your current proposal angle.
```

```text
Your knowledge graph has 18 new connections.
```

## Avoid

```text
Wow! Amazing discoveries await!
```

```text
Supercharge your lab with AI magic!
```

```text
Revolutionize everything instantly!
```

Keep it confident and calm.

---

# 18. Dark Theme Direction

The dark theme should not feel like a generic black dashboard.

It should feel like:

```text
deep forest at night + glowing knowledge network
```

## Dark Theme Design

* background: deep green-black
* cards: dark moss
* text: warm cream
* accents: sage and gold
* mycelium lines: soft glowing green/gold
* Mylo: still bright and readable

Dark mode is especially good for:

* dashboard
* graph visualizations
* research maps
* night/work mode

---

# 19. Design Mistakes to Avoid

## 1. Making it too cute

Mylo is cute, but the product is for research labs. Keep the interface mature.

## 2. Too much illustration

Use Mylo strategically. Do not put him in every single card.

## 3. Weak information hierarchy

The product has many features. Prioritize:

```text
Research Intelligence
Knowledge Graph
Funding/Fellowship Matching
Lab Strategy
```

## 4. Too much text

Use short sections, strong headings, and visual dashboard previews.

## 5. Generic AI styling

Avoid blue neon gradients, robotic imagery, and generic AI node backgrounds. Your differentiator is organic intelligence.

---

# 20. Design System Summary

## Visual Identity

```text
Warm botanical SaaS
```

## Brand Metaphor

```text
A living mycelium network for research knowledge
```

## Mascot Role

```text
Mylo is the scout/agent who searches, connects, alerts, and guides.
```

## UI Shape Language

```text
rounded cards
pill buttons
soft panels
organic dividers
network lines
```

## Primary Colors

```text
cream
forest green
sage
mushroom beige
gold
soft brown
```

## Primary Components

```text
Navbar
Hero
Feature cards
Dashboard cards
Opportunity alerts
Knowledge graph preview
Mylo helper states
CTA panels
```

---

# 21. Practical Front-End Design Rules

Use these constraints when coding:

```text
Max page width: 1200–1280px
Border radius: 16–28px
Button radius: full pill
Card padding: 24–32px
Section padding: 80–120px desktop
Section padding: 48–72px mobile
Hero headline: 64–84px desktop
Body text: 16–18px
Small labels: 12–14px
```

## Spacing

Use generous spacing.

The site should breathe.

Good pattern:

```text
Hero: large open space
Feature strip: compact but readable
Dashboard: dense but contained
Lower sections: alternating spacious blocks
```

---

# 22. Best Implementation Stack

For your front end:

```text
Next.js
Tailwind CSS
Framer Motion
shadcn/ui
Lucide icons
Recharts or custom SVG for graph previews
```

Use Mylo assets as:

```text
SVG if possible
PNG/WebP for illustrations
Lottie later if animated
```

---

# 23. Suggested Homepage Wireframe

```text
-------------------------------------------------
Floating Navbar
-------------------------------------------------

[Badge: Your AI Research Scout]

Living Intelligence
for Research Labs

Subheadline text...

[Get Started] [Meet Mylo]

Trust chips: Trusted by researchers / Privacy-first / Built for labs

                           [Large Mylo]
                    [Floating feature bubbles]
-------------------------------------------------

Feature Strip:
Literature Search | Knowledge Graph | Grant Alerts |
Fellowship Match | Research Planning | Team Guide

-------------------------------------------------

Dashboard Preview:
Sidebar + Research Pulse + Graph + Opportunities + Project Snapshot

-------------------------------------------------

How It Works:
Build Profile → Connect Knowledge → Monitor Signals → Guide Strategy

-------------------------------------------------

Use Cases:
For PIs | For Students | For Teams | For Grant Writers

-------------------------------------------------

Meet Mylo:
Mascot explanation + pose grid

-------------------------------------------------

Final CTA:
Start growing your lab’s research intelligence.

-------------------------------------------------
Footer
-------------------------------------------------
```

---

# Final Design Direction

The site should feel like:

> **A polished research platform where a friendly mushroom scout guides labs through a living network of papers, people, projects, grants, and ideas.**

The best design decision is to keep the **interface professional** and let **Mylo provide personality**.

That gives you a strong balance:

```text
serious enough for labs
friendly enough to remember
unique enough to stand out
simple enough to implement
```
