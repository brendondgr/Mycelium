import { inDemoBrowser } from "@/lib/demo";

const DEFAULT_BROWSER_API_BASE = "/api";
const DEFAULT_SERVER_API_BASE = "http://127.0.0.1:8000/api";

function normalizeBase(base: string): string {
  return base.replace(/\/$/, "");
}

/**
 * Browser-facing API base. Prefer same-origin `/api` (Next.js proxy) in local dev.
 *
 * Under `/demo` it is `<base>/demo`: the backend's demo door
 * (`apps/demo/middleware.py`) serves the same routes there, read-only, as the
 * demo viewer. Every browser call in the app is built on this function, which
 * is what lets the demo reuse the app unchanged.
 */
export function getPublicApiBase(): string {
  const base = normalizeBase(process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_BROWSER_API_BASE);
  return inDemoBrowser() ? `${base}/demo` : base;
}

/** Server-side API base. Always absolute so SSR can reach Django directly. */
export function getServerApiBase(): string {
  if (process.env.API_INTERNAL_URL) {
    return normalizeBase(process.env.API_INTERNAL_URL);
  }

  const publicBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  if (publicBase.startsWith("http://") || publicBase.startsWith("https://")) {
    return normalizeBase(publicBase);
  }

  return DEFAULT_SERVER_API_BASE;
}

/** Build a Django API path with a trailing slash (avoids APPEND_SLASH 301 redirects). */
export function buildApiUrl(base: string, ...segments: string[]): string {
  const path = segments
    .map((segment) => segment.replace(/^\/+|\/+$/g, ""))
    .filter(Boolean)
    .join("/");

  return `${normalizeBase(base)}/${path}/`;
}
