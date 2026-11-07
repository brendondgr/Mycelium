"use client";

import * as React from "react";
import { ExternalLink } from "lucide-react";

import { DocumentIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import { PageSkeleton } from "@/components/portal/skeleton";
import { DetailSection, FeedCard, ItemDetail, PageHead } from "@/components/portal/feed/parts";
import { ReaderLayout, groupByTheme, useReader } from "@/components/portal/feed/reader";
import { FeedToolbar, useFeedControls, type Facet, type SortOption } from "@/components/portal/feed/toolbar";
import { IgnorableCard, IgnoreButton, SaveButton } from "@/components/portal/sections/opportunity-bits";
import { useDailyReport, useLabRecommendations } from "@/lib/portal/hooks";
import { useInfiniteReveal } from "@/lib/portal/use-infinite-reveal";
import type { MyLab, RecommendedMember, Suggestion } from "@/lib/portal/types";

/** How many papers each infinite-scroll slice reveals. */
const PAPER_PAGE_SIZE = 12;

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function byline(s: Suggestion): string {
  const authors = s.authors.length > 1 ? `${s.authors[0]} et al.` : (s.authors[0] ?? "");
  return [authors, s.year ? String(s.year) : ""].filter(Boolean).join(" · ");
}

/**
 * The Research Papers page: one page that scrolls through every paper Mylo
 * matched, grouped by the theme each was matched to, with the opened paper
 * pinned on the right (a drawer on narrow screens). Above the list: a search,
 * a sort, and filter menus — theme, who it is for (lab), what to show, venue.
 *
 * The same component serves a personal and a lab workspace; a lab adds "who
 * it is for" from its `recommended_for`.
 */
export function ResearchPapersSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return <LabPapersFeed lab={currentLab} />;
  }
  return <PersonalResearchPapers />;
}

function LabPapersFeed({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabRecommendations(lab.slug);
  const suggestions = React.useMemo(() => data?.papers ?? [], [data]);
  return (
    <PapersFeed
      suggestions={suggestions}
      isLoading={isLoading}
      isError={isError}
      generatedAt={data?.generated_at ?? null}
      recommendedFor={data?.recommended_for}
      labName={lab.name}
    />
  );
}

function PersonalResearchPapers() {
  const { data, isLoading, isError } = useDailyReport();
  const suggestions = React.useMemo(() => data?.suggestions ?? [], [data]);
  return (
    <PapersFeed
      suggestions={suggestions}
      isLoading={isLoading}
      isError={isError}
      // A sign-up background scan may be filling this feed; surface it.
      scanning={data?.scanning ?? false}
      generatedAt={data?.generated_at ?? null}
    />
  );
}

function usePaperFacets(
  suggestions: Suggestion[],
  recommendedFor?: Record<string, RecommendedMember[]>,
): Facet<Suggestion>[] {
  return React.useMemo(() => {
    const facets: Facet<Suggestion>[] = [];

    const themes = new Map<string, string>();
    for (const s of suggestions) if (s.cluster) themes.set(s.cluster.id, s.cluster.label);
    if (themes.size > 1) {
      facets.push({
        id: "theme",
        label: "Theme",
        mode: "multi",
        options: [...themes].map(([id, label]) => ({
          value: id,
          label,
          test: (s) => s.cluster?.id === id || s.bridge_clusters.some((b) => b.id === id),
        })),
      });
    }

    if (recommendedFor) {
      const people = new Map<string, string>();
      for (const list of Object.values(recommendedFor)) for (const m of list) people.set(m.username, m.name);
      if (people.size) {
        facets.push({
          id: "who",
          label: "Best for",
          mode: "multi",
          options: [...people].map(([username, name]) => ({
            value: username,
            label: name,
            test: (s) => (recommendedFor[s.content_id] ?? []).some((m) => m.username === username),
          })),
        });
      }
    }

    facets.push({
      id: "show",
      label: "Show only",
      mode: "multi",
      options: [
        { value: "new", label: "New this week", test: (s) => s.is_new },
        { value: "saved", label: "Saved", test: (s) => s.saved || s.saved_labs.length > 0 },
        { value: "mylo", label: "Mylo's own picks", test: (s) => s.origin === "llm" },
        { value: "cross", label: "Cross-topic matches", test: (s) => s.origin !== "llm" },
      ],
    });

    const venues = new Map<string, number>();
    for (const s of suggestions) if (s.venue) venues.set(s.venue, (venues.get(s.venue) ?? 0) + 1);
    const top = [...venues].sort((a, b) => b[1] - a[1]).slice(0, 8);
    if (top.length > 1) {
      facets.push({
        id: "venue",
        label: "Venue",
        mode: "multi",
        options: top.map(([venue]) => ({ value: venue, label: venue, test: (s) => s.venue === venue })),
      });
    }
    return facets;
  }, [suggestions, recommendedFor]);
}

function useSorts(suggestions: Suggestion[]): SortOption<Suggestion>[] {
  return React.useMemo(() => {
    const order = new Map(suggestions.map((s, i) => [s.content_id, i]));
    const pos = (s: Suggestion) => order.get(s.content_id) ?? 0;
    return [
      { value: "mylo", label: "Mylo's order", cmp: (a, b) => pos(a) - pos(b) },
      { value: "new", label: "Newest first", cmp: (a, b) => (b.year ?? 0) - (a.year ?? 0) || pos(a) - pos(b) },
      { value: "title", label: "Title A–Z", cmp: (a, b) => (a.headline || a.title).localeCompare(b.headline || b.title) },
    ];
  }, [suggestions]);
}

const paperText = (s: Suggestion) =>
  [s.title, s.headline, s.abstract, s.venue, s.source, s.authors.join(" "), s.cluster?.label ?? ""].join(" ");
const paperId = (s: Suggestion) => s.content_id;

function PapersFeed({
  suggestions,
  isLoading,
  isError,
  scanning = false,
  generatedAt = null,
  recommendedFor,
  labName,
}: {
  suggestions: Suggestion[];
  isLoading: boolean;
  isError: boolean;
  scanning?: boolean;
  generatedAt?: string | null;
  /** Lab-only: content id → the members Mylo judges each paper is for. */
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
}) {
  const facets = usePaperFacets(suggestions, recommendedFor);
  const sorts = useSorts(suggestions);
  const controls = useFeedControls({ items: suggestions, facets, sorts, text: paperText });
  const resetKey = `${controls.query}|${controls.sort}|${JSON.stringify(controls.filters)}`;
  const { visible: shown, hasMore, remaining, sentinelRef, revealMore } = useInfiniteReveal(
    controls.visible,
    PAPER_PAGE_SIZE,
    resetKey,
  );
  const groups = groupByTheme(shown, (s) => s.cluster);
  const reader = useReader(controls.visible, paperId, groups[0]?.items[0]);

  const newCount = suggestions.filter((s) => s.is_new).length;
  const when = formatWhen(generatedAt);
  const lede = isLoading
    ? "Gathering today's papers…"
    : suggestions.length === 0
      ? labName
        ? `Papers Mylo matched to ${labName}.`
        : "Your paper matches, grouped by the theme each one fits."
      : (
          <>
            {suggestions.length} papers {labName ? `Mylo matched to ${labName}` : "matched your research"}
            {newCount ? (
              <>
                , <strong>{newCount} new</strong> this week
              </>
            ) : null}
            {when ? ` · gathered ${when}` : ""}.
          </>
        );

  if (isLoading) {
    return (
      <div className="ws-feedpage">
        <PageSkeleton kind="feed" reader />
      </div>
    );
  }

  return (
    <div className="ws-feedpage" data-layout="reader" data-filters="bar">
      <PageHead kicker={labName ?? "Your feed"} title="Research Papers" lede={lede} />

      {scanning ? (
        <div role="status" aria-live="polite" className="ws-note ws-note-quiet">
          <p className="ws-note-text">Scanning new articles for you… fresh matches will appear here shortly.</p>
        </div>
      ) : null}

      {isError ? (
        <EmptyState
          icon={<DocumentIcon size={28} />}
          title={labName ? "Couldn't load this feed" : "Couldn't load your research papers"}
          description="Something went wrong fetching the papers. Please try again in a moment."
        />
      ) : suggestions.length === 0 ? (
        <EmptyState
          icon={<DocumentIcon size={28} />}
          title={
            labName
              ? "No lab paper matches yet"
              : scanning
                ? "Scanning new articles for you…"
                : "Your first paper suggestions are on their way"
          }
          description={
            labName
              ? "Once Mylo has run for this lab, papers matched to its shared research profile will appear here."
              : scanning
                ? "Your watch topics didn't have enough fresh matches yet, so Mylo is searching new sources now."
                : "Once Mylo's literature scan runs against your research profile, your matching papers — each with why it matters to you — will appear here."
          }
        />
      ) : (
        <>
          <FeedToolbar
            controls={controls}
            items={suggestions}
            facets={facets}
            sorts={sorts}
            placeholder="Search titles, abstracts, authors…"
            noun="papers"
            idPrefix="papers"
          />
          <ReaderLayout
            reader={reader}
            groups={groups}
            getId={paperId}
            label="Research papers"
            empty={
              <div className="ws-empty">
                <p>No papers match these filters.</p>
                <button type="button" className="ws-btn ws-btn-line" onClick={controls.clear}>
                  Clear search and filters
                </button>
              </div>
            }
            renderCard={(s, { selected, onOpen }) => (
              <IgnorableCard contentId={s.content_id} title={s.title}>
                {({ onIgnored }) => (
                  <FeedCard
                    title={s.headline || s.title}
                    signal={
                      <>
                        {s.venue ? <span className="ws-kind">{s.venue}</span> : null}
                        {s.year ? <span className="ws-meta-text">{s.year}</span> : null}
                      </>
                    }
                    isNew={s.is_new}
                    actions={
                      <>
                        <SaveButton contentId={s.content_id} saved={s.saved} savedLabs={s.saved_labs} variant="icon" />
                        <IgnoreButton contentId={s.content_id} title={s.title} onIgnored={onIgnored} />
                      </>
                    }
                    facts={byline(s) ? <span className="ws-meta-text">{byline(s)}</span> : null}
                    reason={s.beats[0] || s.reason}
                    byMylo={s.origin === "llm"}
                    caveat={s.caveat}
                    members={recommendedFor?.[s.content_id]}
                    theme={s.cluster}
                    also={s.bridge_clusters}
                    selected={selected}
                    onOpen={onOpen}
                  />
                )}
              </IgnorableCard>
            )}
            renderDetail={(s) => (
              <ItemDetail
                title={s.title}
                signal={
                  <>
                    {s.venue ? <span className="ws-kind">{s.venue}</span> : null}
                    {s.year ? <span className="ws-meta-text">{s.year}</span> : null}
                    {s.is_new ? <span className="ws-new">New</span> : null}
                  </>
                }
                facts={
                  s.authors.length ? (
                    <p className="ws-meta-text">{s.authors.slice(0, 8).join(", ")}{s.authors.length > 8 ? ", et al." : ""}</p>
                  ) : null
                }
                actions={
                  <>
                    {s.url ? (
                      <a className="ws-btn ws-btn-solid" href={s.url} target="_blank" rel="noopener noreferrer">
                        Read paper <ExternalLink size={13} aria-hidden="true" />
                      </a>
                    ) : null}
                    <SaveButton contentId={s.content_id} saved={s.saved} savedLabs={s.saved_labs} />
                  </>
                }
                byMylo={s.origin === "llm"}
                beats={s.beats}
                reason={s.reason}
                caveat={s.caveat}
                bridgeNote={s.bridge_note}
                members={recommendedFor?.[s.content_id]}
                showMembers={Boolean(labName)}
                theme={s.cluster}
                also={s.bridge_clusters}
                source={<span>Source · {[s.source, s.venue].filter(Boolean).join(" · ")}</span>}
              >
                {s.abstract ? (
                  <DetailSection title="Abstract">
                    <p>{s.abstract}</p>
                  </DetailSection>
                ) : null}
              </ItemDetail>
            )}
            after={
              <FeedSentinel
                sentinelRef={sentinelRef}
                hasMore={hasMore}
                remaining={remaining}
                onRevealMore={revealMore}
                totalShown={shown.length}
                noun="papers"
              />
            }
          />
        </>
      )}
    </div>
  );
}
