import type { FeedItem } from "@/data/feed-preview";

/**
 * The measured match a preview card states — a port of `matchInfo` in
 * `web/app/src/components/portal/feed/parts.tsx`, so the figures on the public
 * site are derived the same way the app derives them.
 *
 * `embeddingMatch` is the item's embedding similarity to the reader's profile
 * (the API's `embedding_match`, 0–100): the overall figure. Each theme carries a
 * fusion `score` (the API's `per_cluster`), which is not a percentage — it runs
 * past 1 — so a theme's figure is the overall similarity scaled by how strongly
 * that theme pulled the item relative to the theme that pulled it most.
 */
export type ThemeMatch = { label: string; token: string; pct: number };

export type MatchInfo = { overall: number; themes: ThemeMatch[] };

export function matchInfo(item: FeedItem): MatchInfo {
  const overall = item.embeddingMatch;
  const top = Math.max(0, ...item.themes.map((t) => t.score));
  const themes = item.themes.map((t) => ({
    label: t.label,
    token: t.token,
    pct: top > 0 ? Math.round((overall * t.score) / top) : overall,
  }));
  // Strongest first; the attributed theme wins a tie because it came first.
  themes.sort((a, b) => b.pct - a.pct);
  return { overall, themes };
}

const DAY = 86_400_000;

/**
 * The preview's dates are offsets from the day the site is built, not fixed
 * dates: a fictional deadline written as "Sep 1" would read as closed months
 * after the page shipped. Formatted as the app's `DeadlinePill` formats them.
 */
export function daysFromBuild(offset: number): string {
  const d = new Date(Date.now() + offset * DAY);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** "Mar 4 – 9, 2027", or across months "Mar 30 – Apr 3, 2027". */
export function eventRange(start: number, length: number): string {
  const a = new Date(Date.now() + start * DAY);
  const b = new Date(Date.now() + (start + length - 1) * DAY);
  const month = (d: Date) => d.toLocaleDateString("en-US", { month: "short" });
  const head = `${month(a)} ${a.getDate()}`;
  const tail = month(a) === month(b) ? `${b.getDate()}` : `${month(b)} ${b.getDate()}`;
  return `${head} – ${tail}, ${b.getFullYear()}`;
}

export function daysLeft(days: number): string {
  return days === 0 ? "today" : days === 1 ? "1 day" : `${days} days`;
}

/* The same item can appear twice on one page (the feed tabs and the tour), so a
   card's breakdown id is numbered here, at module level — an Astro component's
   frontmatter runs afresh for every render and cannot hold a counter. */
let serial = 0;

export function nextId(): string {
  serial += 1;
  return String(serial);
}
