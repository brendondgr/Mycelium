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

export const primaryNav = [
  { href: "/", label: "Home" },
  { href: "/product", label: "Product" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
] as const;

export const footerNav = {
  product: [
    { href: "/product", label: "How it works" },
    { href: "/#self-host", label: "Self-host" },
    { href: sourceRepoUrl, label: "Source code" },
  ],
  company: [
    { href: "/about", label: "About" },
    { href: "/contact", label: "Contact" },
    { href: appLoginUrl, label: "Log in" },
    { href: appSignupUrl, label: "Sign up" },
  ],
} as const;
