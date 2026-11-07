"use client";

import * as React from "react";
import { Search as SearchIcon, UserRound } from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import { FEEDS, PEOPLE, SEARCH_SUGGESTIONS, type FeedKind } from "@/components/labs/preview/fixtures";
import { searchText } from "@/components/labs/preview/feeds";
import { FeedCard } from "@/components/labs/preview/parts";

const KINDS: { kind: FeedKind; label: string }[] = [
  { kind: "paper", label: "Papers" },
  { kind: "grant", label: "Grants" },
  { kind: "fellowship", label: "Fellowships" },
  { kind: "conference", label: "Conferences" },
];

const CARD = ["reason", "who", "themes"];

function matches(text: string, q: string) {
  const words = q.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
  if (words.length === 0) return true;
  const hay = text.toLowerCase();
  return words.some((w) => hay.includes(w));
}

/** The decoration around the box — the option that replaces today's vine. */
function Frame({ kind }: { kind: string }) {
  if (kind === "threads") {
    return (
      <svg className="lx-search-threads" viewBox="0 0 600 60" preserveAspectRatio="none" aria-hidden="true">
        <path d="M40 0 Q60 30 30 58" />
        <path d="M120 0 Q110 22 140 44" />
        <path d="M300 0 Q290 30 310 56" />
        <path d="M470 0 Q500 26 480 50" />
        <path d="M560 0 Q545 20 575 40" />
      </svg>
    );
  }
  if (kind === "vine") {
    return (
      <svg className="lx-search-vine" viewBox="0 0 600 80" preserveAspectRatio="none" aria-hidden="true">
        <path d="M6 70 C 40 2, 120 90, 200 10 S 360 80, 420 8 S 560 70, 594 12" />
        {[60, 180, 300, 420, 540].map((x, i) => (
          <ellipse key={x} cx={x} cy={i % 2 ? 22 : 58} rx="9" ry="4" transform={`rotate(${i % 2 ? -30 : 30} ${x} ${i % 2 ? 22 : 58})`} />
        ))}
      </svg>
    );
  }
  return null;
}

export function SearchPage({ o }: { o: Record<string, OptionValue> }) {
  const [query, setQuery] = React.useState("sea surface height");
  const centered = o.entry === "centered";

  const results = KINDS.map((k) => ({
    ...k,
    items: FEEDS[k.kind].filter((i) => matches(searchText(i), query)),
  }));
  const people = PEOPLE.filter((p) => matches(`${p.name} ${p.why}`, query));
  const total = results.reduce((n, r) => n + r.items.length, 0) + people.length;

  const peopleList = (
    <ul className="lx-people">
      {people.map((p) => (
        <li key={p.name} className="lx-item lx-rise">
          <span className="lx-avatar" aria-hidden="true">
            <UserRound size={15} />
          </span>
          <span>
            <span className="lx-compact-title lx-static">{p.name}</span>
            <span className="lx-meta-text"> · {p.role}</span>
            <span className="lx-compact-why">{p.why}</span>
          </span>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="lx-search" data-entry={o.entry as string}>
      <div className="lx-search-entry lx-rise">
        {centered ? (
          <>
            <p className="lx-kicker">Search</p>
            <h1 className="lx-h lx-page-title">The whole corpus, ranked for your lab.</h1>
          </>
        ) : (
          <h1 className="lx-h lx-page-title lx-search-title-compact">Search</h1>
        )}
        <div className="lx-search-box" data-frame={o.frame as string}>
          <Frame kind={o.frame as string} />
          <SearchIcon size={18} aria-hidden="true" className="lx-search-icon" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Papers, grants, people, methods…"
            aria-label="Search the corpus"
          />
          <kbd className="lx-kbd">⌘K</kbd>
        </div>
        {o.suggestions ? (
          <div className="lx-chips lx-suggest" role="group" aria-label="Suggested searches">
            {SEARCH_SUGGESTIONS.map((s) => (
              <button key={s} type="button" className="lx-chip" aria-pressed={query === s} onClick={() => setQuery(s)}>
                {s}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <p className="lx-meta-text lx-result-count" aria-live="polite">
        {total} results for “{query || "everything"}”
      </p>

      {o.results === "grouped" ? (
        <div className="lx-result-groups">
          {results.map((r) =>
            r.items.length ? (
              <section key={r.kind} className="lx-feed-group" aria-label={r.label}>
                <h2 className="lx-group-label">
                  {r.label} <span className="lx-count">{r.items.length}</span>
                </h2>
                <div className="lx-feed-items">
                  {r.items.map((i) => (
                    <FeedCard key={i.id} item={i} show={CARD} />
                  ))}
                </div>
              </section>
            ) : null,
          )}
          {people.length ? (
            <section className="lx-feed-group" aria-label="People">
              <h2 className="lx-group-label">
                People <span className="lx-count">{people.length}</span>
              </h2>
              {peopleList}
            </section>
          ) : null}
        </div>
      ) : (
        <div className="lx-feed-items">
          {results
            .flatMap((r) => r.items)
            .map((i) => (
              <FeedCard key={i.id} item={i} show={CARD} />
            ))}
          {people.length ? peopleList : null}
        </div>
      )}
      {total === 0 ? <p className="lx-empty">Nothing matched. Try one of your themes above.</p> : null}
    </div>
  );
}
