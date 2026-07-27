export const siteName = "Mycelium";

export const siteTagline = "Living intelligence for research labs";

// This site and the authenticated app share one origin behind the nginx
// gateway (`/` → landing, `/login`, `/signup` and `/app` → Next), so app links
// stay relative and follow whatever host the visitor arrived on — localhost, a
// tunnel domain, a real domain. Hardcoding an absolute base here sent every
// visitor on a public hostname back to http://localhost:11050/login. Set
// PUBLIC_APP_URL only when the app genuinely lives on a different origin.
const appBaseUrl = (import.meta.env.PUBLIC_APP_URL ?? "").replace(/\/$/, "");

export const appLoginUrl = `${appBaseUrl}/login`;

/**
 * The primary conversion target for the whole public site. Every "Start free"
 * button points here — the real signup the gateway already routes — rather
 * than at a lead-capture placeholder.
 */
export const appSignupUrl = `${appBaseUrl}/signup`;

export const primaryCta = {
  href: appSignupUrl,
  label: "Start free",
  /** Used under hero and final-CTA buttons, never as the button label. */
  note: "14-day trial · no credit card",
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

export const primaryNav = [
  { href: "/", label: "Home" },
  { href: "/product", label: "Product" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
] as const;

export const footerNav = {
  product: [
    { href: "/product", label: "How it works" },
    { href: "/pricing", label: "Pricing" },
    { href: appSignupUrl, label: "Start free" },
  ],
  company: [
    { href: "/about", label: "About" },
    { href: "/contact", label: "Contact" },
    { href: appLoginUrl, label: "Log in" },
  ],
} as const;
