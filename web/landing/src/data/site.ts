export const siteName = "Mycelium";

export const siteTagline = "Living intelligence for research labs";

const appBaseUrl = (
  import.meta.env.PUBLIC_APP_URL ?? "http://localhost:9911"
).replace(/\/$/, "");

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
