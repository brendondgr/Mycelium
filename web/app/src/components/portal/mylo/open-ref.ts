"use client";

import { projectRoute, routeWithScope, SECTION_ROUTES } from "@/lib/portal/routes";

import { openItemInReader } from "./events";

/**
 * Where a thread reference opens. An item opens in the reader of the page
 * already showing it; otherwise in the feed for its kind, which the agent
 * names in the title it gives the item ("[grant] …").
 */

export const FEED_FOR_KIND: Record<string, string> = {
  paper: SECTION_ROUTES.papers,
  grant: SECTION_ROUTES.opportunities,
  fellowship: SECTION_ROUTES.fellowships,
  conference: SECTION_ROUTES.conferences,
};

const KIND_PREFIX = /^\[(paper|grant|fellowship|conference)\]\s*/i;

/** "[paper] Cell segmentation" → { kind: "paper", title: "Cell segmentation" }. */
export function splitItemTitle(title: string): { kind: string | null; title: string } {
  const m = KIND_PREFIX.exec(title);
  return m ? { kind: m[1].toLowerCase(), title: title.slice(m[0].length) } : { kind: null, title };
}

export function refHref(ref: { kind: string; key: string; title?: string }): string | null {
  switch (ref.kind) {
    case "item": {
      const { kind } = splitItemTitle(ref.title ?? "");
      const feed = (kind && FEED_FOR_KIND[kind]) || SECTION_ROUTES.papers;
      return `${feed}?item=${encodeURIComponent(ref.key)}`;
    }
    case "project":
      return projectRoute(ref.key);
    case "lab":
      return routeWithScope(SECTION_ROUTES.overview, ref.key);
    case "department":
      return `/app/department/${encodeURIComponent(ref.key)}`;
    default:
      return null;
  }
}

/** Open a reference: in place when the page shows it, else by navigating. */
export function openRef(
  ref: { kind: string; key: string; title?: string },
  navigate: (href: string) => void,
  fallback?: string,
) {
  if (
    ref.kind === "item" &&
    openItemInReader(ref.key, splitItemTitle(ref.title ?? "").kind ?? "paper")
  )
    return;
  const href = fallback ?? refHref(ref);
  if (href) navigate(href);
}
