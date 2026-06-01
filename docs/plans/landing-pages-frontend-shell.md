# Landing Pages Frontend Shell Plan

## Objective

Create the public landing-page shell for Mycelium in `web/landing`, using the
existing Astro site to present the product as warm, scholarly lab intelligence.
The first implementation should establish the outer public-site experience:
floating header, image-led hero, supporting product sections, route structure,
responsive behavior, and validation expectations.

The hero section should use `web/art/frontpage/MyloHero.png` as the primary
visual, with headline and supporting copy overlaid toward the side in the spirit
of the supplied reference image.

## Assumptions And Open Questions

- The user requested `web/art/frontpage/MyHero.png`, but the repository contains
  `web/art/frontpage/MyloHero.png`. This plan assumes `MyloHero.png` is the
  intended asset unless a new `MyHero.png` is added.
- Public landing pages are owned by `web/landing` because `docs/skills/website-architecture.md`
  assigns Astro to public/content-heavy routes.
- The authenticated workspace remains in `web/app`; this work should only link
  to login/app entry points and should not build authenticated screens.
- Pricing can begin as a pilot/contact-oriented page if final commercial tiers
  are not decided.
- CTA actions can initially use placeholder routes such as `/demo`, `/contact`,
  or `/login` until backend auth and lead capture contracts are defined.

## Implementation Phases

### 1. Confirm Public Site Foundation

- Keep the public site in `web/landing`.
- Review `web/landing/src/pages/index.astro`, `web/landing/src/styles/global.css`,
  `web/packages/config/src/theme.css`, and `web/landing/package.json`.
- Verify the root commands remain:
  - `npm run dev:landing`
  - `npm --prefix web/landing run build`
  - `npm --prefix web/landing run lint`
- Add only landing-site dependencies that are already part of the intended stack:
  Astro, Tailwind, MDX, GSAP, light React islands, Radix/shadcn primitives, and
  Lucide icons.

### 2. Define Landing Route Map

Create or reserve public routes:

- `/` for the full front page.
- `/product` for the product story and output examples.
- `/solutions` for role and lab use cases.
- `/resources` for research notes, docs, or launch content.
- `/pricing` for pilot/pricing information.
- `/about` for mission, trust, and Mylo/brand story.
- `/demo` or `/contact` for interest capture.
- `/login` as the public entry into the authenticated app.

Initial implementation can place most routes behind simple shell pages if the
front page is the first detailed deliverable.

### 3. Build The Shared Public Shell

- Add a reusable public layout for metadata, global styles, skip link, and page
  structure.
- Add a floating navigation header that includes:
  - Mycelium logo/brand lockup.
  - Product, Solutions, Resources, Pricing, and About links.
  - Log in link.
  - Primary CTA.
  - Mobile menu with keyboard support and visible focus states.
- Add a shared footer with product links, trust language, and legal/contact
  placeholders.
- Keep the shell light and content-forward, not app-heavy.

### 4. Implement The Front Page

The front page should follow the documented public-site sequence:

- Floating navigation.
- Hero with `web/art/frontpage/MyloHero.png`, side-positioned text overlay,
  concise product promise, supporting copy, and two CTAs.
- Feature strip for discovering literature, connecting knowledge, finding
  grants/fellowships, and guiding research strategy.
- Product dashboard preview that shows realistic research pulse, knowledge
  connections, opportunity alerts, project snapshots, and next actions.
- How it works section explaining lab profile, monitoring, evidence graph, and
  reviewed recommendations.
- Use cases for PIs, students/postdocs, grant writers, and lab administrators.
- Meet Mylo section that treats Mylo as a product guide, not decoration.
- Final CTA and footer.

Recommended hero copy direction:

- H1: `Living intelligence for research labs`
- Supporting copy: explain that Mycelium connects lab goals, literature,
  evidence, grants, fellowships, reports, and next actions.
- CTAs: `Get started` and `Meet Mylo` or `Request a demo`.

### 5. Visual System And Responsive Behavior

- Use the canonical palette from `docs/styles.md` and shared theme tokens:
  cream background, forest and moss greens, sage accents, mushroom beige, soft
  brown, and restrained gold.
- Use a scholarly serif direction for major headings and a clean sans-serif for
  UI/body text.
- Keep cards at 8px radius or less unless existing tokens decide otherwise.
- Avoid generic SaaS blue, neon AI visuals, heavy gradients, decorative clutter,
  and excessive mascot repetition.
- Make `MyloHero.png` the first-viewport signal. On desktop, position text over
  the image toward the left/side while preserving Mylo visibility. On mobile,
  keep text readable by using a controlled overlay treatment or stacking that
  still shows the image clearly.
- Ensure the first viewport hints at the next section on common desktop and
  mobile sizes.
- Respect `prefers-reduced-motion`; keep any node/line motion subtle.

### 6. Accessibility, Security, And Data Boundaries

- Meet WCAG 2.2 AA expectations for contrast, semantics, keyboard navigation,
  focus states, alt text, reduced motion, and responsive text.
- Include meaningful alt text for `MyloHero.png`.
- Do not expose private lab data in public previews. Use clearly fictional or
  generic sample dashboard data.
- Public lead/demo forms, if added later, should post through an approved Django
  API endpoint with validation, rate limiting, spam protection, and logging.
- Login/app links should route to the authenticated boundary without embedding
  authenticated logic in the Astro site.

### 7. Validation And Acceptance Criteria

- `npm --prefix web/landing run lint` passes.
- `npm --prefix web/landing run build` passes.
- Manual viewport checks cover at least mobile, tablet, laptop, and wide desktop.
- Header, mobile menu, CTAs, and links are keyboard reachable with visible focus.
- Hero text remains readable over `MyloHero.png` without hiding the main Mylo
  figure.
- No horizontal overflow appears at common mobile widths.
- Public copy aligns with `docs/purpose.md`, `docs/styles.md`, and `docs/goals.md`.
- The page demonstrates product value through realistic outputs, not only
  decoration.

## Public Interfaces And Files Expected To Change

- `web/landing/src/pages/index.astro`
- `web/landing/src/pages/*.astro` or `*.mdx` for public route shells
- `web/landing/src/components/*` for header, footer, hero, section, and preview
  components
- `web/landing/src/styles/global.css`
- `web/packages/config/src/theme.css` only if shared tokens need small additions
- `docs/changelog.md`

## Explicit Exclusions

- No authenticated dashboard implementation in `web/app`.
- No Django API or database work unless a public lead/demo form is explicitly
  added.
- No production pricing model decision beyond placeholder pilot/contact copy.
- No new product direction outside the existing purpose, style, and goals docs.
- No commit for this planning task, per user request.
