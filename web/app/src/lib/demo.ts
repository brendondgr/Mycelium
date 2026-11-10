/**
 * The public demo's paths (see `docs/architecture.md`, "The public demo").
 *
 * `/demo/*` is the workspace under `/app/*`, reached by a rewrite in
 * `src/proxy.ts`: the same pages and components, nothing forked. Two things
 * make that work, and both live here:
 *
 * - **Links.** A link written as `/app/…` must become `/demo/…` while the
 *   visitor is in the demo, or one click takes them out of it. Components get
 *   the right form from `useAppHref()` / `useAppRouter()`
 *   (`components/demo/demo-context.tsx`), which call {@link toDemoPath}.
 * - **Reading the URL.** Code that parses the pathname (which section is
 *   active, which project is open) reads {@link canonicalPath}, so `/demo/grants`
 *   and `/app/grants` parse the same — and the server render, which sees the
 *   rewritten path, agrees with the browser, which sees the original.
 *
 * Pure functions, safe on the server and in the browser.
 */

export const DEMO_BASE = "/demo";
const APP_BASE = "/app";

/** Fired when the demo's API refuses a change; the demo banner says so. */
export const DEMO_REFUSED_EVENT = "mycelium:demo-refused";

/** Tell the banner, when `body` is the demo's read-only refusal. */
export function noteDemoRefusal(body: unknown): void {
  if (
    typeof window !== "undefined" &&
    !!body &&
    typeof body === "object" &&
    (body as Record<string, unknown>).code === "demo_read_only"
  ) {
    window.dispatchEvent(new Event(DEMO_REFUSED_EVENT));
  }
}

/** Request header `src/proxy.ts` sets on a rewritten demo request. */
export const DEMO_HEADER = "x-mycelium-demo";

function under(path: string, base: string): boolean {
  return (
    path === base ||
    path.startsWith(`${base}/`) ||
    path.startsWith(`${base}?`) ||
    path.startsWith(`${base}#`)
  );
}

/** Whether a pathname (or href) is in the demo. */
export function isDemoPath(path: string): boolean {
  return under(path, DEMO_BASE);
}

/** `/app/x?y` → `/demo/x?y`; anything else is returned unchanged. */
export function toDemoPath(href: string): string {
  return under(href, APP_BASE) ? `${DEMO_BASE}${href.slice(APP_BASE.length)}` : href;
}

/** `/demo/x` → `/app/x`, so pathname parsers see one shape. */
export function canonicalPath(pathname: string): string {
  return isDemoPath(pathname) ? `${APP_BASE}${pathname.slice(DEMO_BASE.length)}` : pathname;
}

/** In the browser: is this page under `/demo`? `false` on the server. */
export function inDemoBrowser(): boolean {
  return typeof window !== "undefined" && isDemoPath(window.location.pathname);
}
