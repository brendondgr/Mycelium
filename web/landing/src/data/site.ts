export const siteName = "Mycelium";

export const siteTagline = "An academic research assistant any lab can run on its own computers";

// This site and the authenticated app share one origin behind the nginx
// gateway (`/` → landing, `/login`, `/signup` and `/app` → Next), so app links
// stay relative and follow whatever host the visitor arrived on — localhost, a
// tunnel domain, a real domain. Hardcoding an absolute base here sent every
// visitor on a public hostname back to http://localhost:11050/login. Set
// PUBLIC_APP_URL only when the app genuinely lives on a different origin.
const appBaseUrl = (import.meta.env.PUBLIC_APP_URL ?? "").replace(/\/$/, "");

export const appLoginUrl = `${appBaseUrl}/login`;

/**
 * The primary conversion target for the whole public site. Every "Sign up"
 * button points here — the real signup the gateway already routes — rather
 * than at a lead-capture placeholder.
 */
export const appSignupUrl = `${appBaseUrl}/signup`;

export const primaryCta = {
  href: appSignupUrl,
  label: "Sign up",
  /** Used under hero and final-CTA buttons, never as the button label. */
  note: "Free with a sign-up code · open source",
} as const;

/**
 * Where the source lives. Mycelium is being released as open source, so the
 * second way in — after signing up here — is running it yourself.
 */
export const sourceRepoUrl = "https://github.com/brendondgr/Mycelium";

/**
 * The public demo: a fictional lab in the real app, served by Next behind the
 * same nginx origin. The operator can switch it off, so every link to it is
 * rendered `hidden` with `data-demo-link` and revealed only when
 * `GET /api/demo/status/` says it is on (the inline script in
 * `PublicLayout.astro`). Never link here without that attribute.
 */
export const demoUrl = `${appBaseUrl}/demo`;

export const selfHostCta = {
  href: "/#self-host",
  label: "Run it yourself",
} as const;

export const secondaryCta = {
  href: "/contact",
  label: "Talk to us",
} as const;

/**
 * TODO: replace with the real inbox before launch. This is the only address
 * published on the public site, so it is deliberately a single constant.
 */
export const contactEmail = "hello@mycelium.example";

/**
 * The header's pages. The front page carries what the Product and About pages
 * used to (both now redirect to `/`, see `astro.config.mjs`); Demo and Source
 * follow these in the header itself. `icon` names a glyph in `SiteHeader`.
 */
export const primaryNav = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/contact", label: "Contact", icon: "contact" },
] as const;

export const footerNav = {
  product: [
    { href: "/#how-it-works", label: "How it works" },
    { href: "/#covers", label: "What it covers" },
    { href: "/#mylo", label: "Ask Mylo" },
    { href: "/#self-host", label: "Self-host" },
    { href: sourceRepoUrl, label: "Source code" },
  ],
  company: [
    { href: "/contact", label: "Contact" },
    { href: appLoginUrl, label: "Log in" },
    { href: appSignupUrl, label: "Sign up" },
  ],
} as const;
