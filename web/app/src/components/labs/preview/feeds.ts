/**
 * What each feed can be searched, sorted, filtered and grouped by.
 *
 * The facets mirror the real filter rails (`portal/sections/*-filters.tsx`)
 * minus the ones that only existed to slice a match percent: a feed card no
 * longer shows a percent, so "Match strength" has nothing to stand on.
 */

import type { FeedKey } from "@/components/labs/schema";
import {
  CONFERENCES,
  FELLOWSHIPS,
  GRANTS,
  MEMBERS,
  PAPERS,
  THEMES,
  themeOf,
  type FeedItem,
} from "@/components/labs/preview/fixtures";

export type FacetOption = { value: string; label: string; test: (i: FeedItem) => boolean };

export type Facet = {
  id: string;
  label: string;
  /** "multi": any ticked value matches. "single": one choice, the first means "any". */
  mode: "multi" | "single";
  options: FacetOption[];
};

export type Sort = { value: string; label: string; cmp: (a: FeedItem, b: FeedItem) => number };

export type FeedConfig = {
  key: FeedKey;
  title: string;
  noun: string;
  items: FeedItem[];
  lede: string;
  searchPlaceholder: string;
  sorts: Sort[];
  facets: Facet[];
};

const any: FacetOption = { value: "any", label: "Any", test: () => true };

const themeFacet: Facet = {
  id: "theme",
  label: "Theme",
  mode: "multi",
  options: THEMES.map((t) => ({
    value: t.id,
    label: t.label,
    test: (i) => i.theme === t.id || i.also.includes(t.id),
  })),
};

const forFacet: Facet = {
  id: "for",
  label: "Best for",
  mode: "multi",
  options: MEMBERS.map((m) => ({
    value: m.id,
    label: m.name,
    test: (i) => i.suggested.some((s) => s.member === m.id),
  })),
};

const showOnly: Facet = {
  id: "only",
  label: "Show only",
  mode: "multi",
  options: [
    { value: "new", label: "New this week", test: (i) => i.isNew },
    { value: "saved", label: "Saved", test: (i) => i.saved },
    { value: "mylo", label: "Mylo's reasoning", test: (i) => i.byMylo },
  ],
};

function closes(i: FeedItem): number {
  return "closesIn" in i ? i.closesIn : 999;
}

function deadlineFacet(label = "Deadline"): Facet {
  const within = (d: number) => (i: FeedItem) => closes(i) >= 0 && closes(i) <= d;
  return {
    id: "deadline",
    label,
    mode: "single",
    options: [
      any,
      { value: "d14", label: "Within 2 weeks", test: within(14) },
      { value: "d30", label: "Within 30 days", test: within(30) },
      { value: "d90", label: "Within 90 days", test: within(90) },
    ],
  };
}

const byRank = { value: "best", label: "Best match", cmp: () => 0 };
const byDeadline: Sort = {
  value: "deadline",
  label: "Closing soonest",
  cmp: (a, b) => {
    const da = closes(a) < 0 ? 999 : closes(a);
    const db = closes(b) < 0 ? 999 : closes(b);
    return da - db;
  },
};
const FOUND_ORDER = { today: 0, yesterday: 1, "this week": 2 } as const;
const byNewest: Sort = {
  value: "newest",
  label: "Newest",
  cmp: (a, b) => FOUND_ORDER[a.found] - FOUND_ORDER[b.found],
};

export const FEED_CONFIGS: Record<FeedKey, FeedConfig> = {
  papers: {
    key: "papers",
    title: "Papers",
    noun: "papers",
    items: PAPERS,
    lede: "Ranked within each of the lab's four themes.",
    searchPlaceholder: "Search papers, authors, venues…",
    sorts: [byRank, byNewest],
    facets: [
      themeFacet,
      {
        id: "found",
        label: "Found",
        mode: "single",
        options: [
          any,
          { value: "today", label: "Today", test: (i) => i.found === "today" },
          { value: "week", label: "This week", test: () => true },
        ],
      },
      {
        id: "venue",
        label: "Venue",
        mode: "multi",
        options: [
          { value: "preprint", label: "Preprints", test: (i) => i.kind === "paper" && i.venueType === "preprint" },
          { value: "journal", label: "Journals", test: (i) => i.kind === "paper" && i.venueType === "journal" },
          { value: "conference", label: "Conference papers", test: (i) => i.kind === "paper" && i.venueType === "conference" },
        ],
      },
      forFacet,
      showOnly,
    ],
  },
  grants: {
    key: "grants",
    title: "Grants",
    noun: "grants",
    items: GRANTS,
    lede: "Open calls that fit the lab's themes.",
    searchPlaceholder: "Search grants, sponsors, programs…",
    sorts: [byRank, byDeadline, byNewest],
    facets: [
      themeFacet,
      deadlineFacet(),
      {
        id: "sponsor",
        label: "Sponsor",
        mode: "multi",
        options: Array.from(new Set(GRANTS.map((g) => g.sponsor))).map((sp) => ({
          value: sp,
          label: sp,
          test: (i) => i.kind === "grant" && i.sponsor === sp,
        })),
      },
      {
        id: "eligible",
        label: "Can we apply?",
        mode: "single",
        options: [
          any,
          {
            value: "clear",
            label: "No blockers",
            test: (i) => i.kind === "grant" && !i.checks.some((c) => c.status === "block"),
          },
          {
            value: "ready",
            label: "Every check met",
            test: (i) => i.kind === "grant" && i.checks.every((c) => c.status === "ok"),
          },
        ],
      },
      forFacet,
      showOnly,
    ],
  },
  fellowships: {
    key: "fellowships",
    title: "Fellowships",
    noun: "fellowships",
    items: FELLOWSHIPS,
    lede: "Matched to the people in the lab, with eligibility checked against each profile.",
    searchPlaceholder: "Search fellowships, sponsors…",
    sorts: [{ ...byRank, label: "Best fit" }, byDeadline, byNewest],
    facets: [
      {
        id: "eligible",
        label: "Eligibility",
        mode: "single",
        options: [
          any,
          { value: "qualified", label: "Someone qualifies", test: (i) => i.kind === "fellowship" && i.qualified },
        ],
      },
      {
        id: "stage",
        label: "Academic stage",
        mode: "multi",
        options: ["MS", "PhD", "Postdoc", "Faculty"].map((st) => ({
          value: st,
          label: st,
          test: (i) => i.kind === "fellowship" && i.stages.includes(st),
        })),
      },
      {
        id: "citizenship",
        label: "Citizenship",
        mode: "single",
        options: [
          any,
          { value: "open", label: "Open to any nationality", test: (i) => i.kind === "fellowship" && i.citizenship === "any" },
        ],
      },
      deadlineFacet(),
      { ...themeFacet, label: "Research field" },
      forFacet,
      showOnly,
    ],
  },
  conferences: {
    key: "conferences",
    title: "Conferences",
    noun: "conferences",
    items: CONFERENCES,
    lede: "Where the lab's work could be presented, and what is still open.",
    searchPlaceholder: "Search conferences, places…",
    sorts: [{ ...byRank, label: "Best fit" }, byDeadline, {
      value: "event",
      label: "Event date",
      cmp: (a, b) => (a.kind === "conference" && b.kind === "conference" ? a.eventIn - b.eventIn : 0),
    }],
    facets: [
      {
        id: "submissions",
        label: "Submissions",
        mode: "single",
        options: [
          any,
          { value: "open", label: "Open", test: (i) => i.kind === "conference" && i.open },
          { value: "closed", label: "Closed — attend only", test: (i) => i.kind === "conference" && !i.open },
        ],
      },
      deadlineFacet("Submission deadline"),
      {
        id: "event",
        label: "Event date",
        mode: "single",
        options: [
          any,
          { value: "m3", label: "Within 3 months", test: (i) => i.kind === "conference" && i.eventIn <= 92 },
          { value: "m6", label: "Within 6 months", test: (i) => i.kind === "conference" && i.eventIn <= 183 },
        ],
      },
      {
        id: "region",
        label: "Region",
        mode: "multi",
        options: Array.from(new Set(CONFERENCES.map((c) => c.continent))).map((ct) => ({
          value: ct,
          label: ct,
          test: (i) => i.kind === "conference" && i.continent === ct,
        })),
      },
      {
        id: "ranked",
        label: "Ranking",
        mode: "single",
        options: [
          any,
          { value: "ranked", label: "Has a rank badge", test: (i) => i.kind === "conference" && Boolean(i.rank) },
        ],
      },
      { ...themeFacet, label: "Subject" },
      showOnly,
    ],
  },
};

export type FilterState = Record<string, string[]>;

export function applyFilters(items: FeedItem[], facets: Facet[], state: FilterState): FeedItem[] {
  return items.filter((item) =>
    facets.every((f) => {
      const picked = state[f.id] ?? [];
      if (picked.length === 0 || (f.mode === "single" && picked[0] === "any")) return true;
      return f.options.some((o) => picked.includes(o.value) && o.test(item));
    }),
  );
}

export function searchText(i: FeedItem): string {
  const parts = [i.title, i.reason, themeOf(i.theme).label, i.source];
  switch (i.kind) {
    case "paper":
      parts.push(i.authors, i.venue, i.abstract);
      break;
    case "grant":
      parts.push(i.funder, i.program, i.amount);
      break;
    case "fellowship":
      parts.push(i.sponsor, i.amount, i.stages.join(" "));
      break;
    case "conference":
      parts.push(i.acronym, i.where, i.continent);
      break;
  }
  return parts.join(" ").toLowerCase();
}

export type Group = { key: string; label: string; items: FeedItem[] };

export function groupItems(items: FeedItem[], by: string): Group[] {
  if (by === "none") return [{ key: "all", label: "", items }];
  if (by === "theme") {
    return THEMES.map((t) => ({ key: t.id, label: t.label, items: items.filter((i) => i.theme === t.id) })).filter(
      (g) => g.items.length > 0,
    );
  }
  if (by === "day") {
    return (["today", "yesterday", "this week"] as const)
      .map((d) => ({ key: d, label: d[0].toUpperCase() + d.slice(1), items: items.filter((i) => i.found === d) }))
      .filter((g) => g.items.length > 0);
  }
  // Month: closing month for grants and fellowships, event month for conferences.
  const monthOf = (i: FeedItem) => ("month" in i ? i.month : "");
  const months: string[] = [];
  for (const i of items) if (!months.includes(monthOf(i))) months.push(monthOf(i));
  return months.map((m) => ({ key: m, label: m, items: items.filter((i) => monthOf(i) === m) }));
}
