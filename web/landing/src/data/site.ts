export const siteName = "Mycelium";

export const siteTagline = "Living intelligence for research labs";

// This site and the authenticated app share one origin behind the nginx
// gateway (`/` → landing, `/login` and `/app` → Next), so app links stay
// relative and follow whatever host the visitor arrived on — localhost, a
// tunnel domain, a real domain. Hardcoding an absolute base here sent every
// visitor on a public hostname back to http://localhost:11050/login. Set
// PUBLIC_APP_URL only when the app genuinely lives on a different origin.
const appBaseUrl = (import.meta.env.PUBLIC_APP_URL ?? "").replace(/\/$/, "");

export const appLoginUrl = `${appBaseUrl}/login`;

export const primaryNav = [
  { href: "/product", label: "Product" },
  { href: "/solutions", label: "Solutions" },
  { href: "/resources", label: "Resources" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
] as const;

export const footerNav = {
  product: [
    { href: "/product", label: "Product overview" },
    { href: "/solutions", label: "Solutions" },
    { href: "/pricing", label: "Pricing" },
  ],
  company: [
    { href: "/about", label: "About" },
    { href: "/contact", label: "Contact" },
    { href: "/demo", label: "Request a demo" },
  ],
  resources: [
    { href: "/resources", label: "Resources" },
    { href: "/research", label: "Research notes" },
  ],
} as const;
