"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import {
  FeedSearchBar,
  clusterOptions,
} from "@/components/portal/primitives/feed-search-bar";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { DocumentIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import { RevealOnScroll } from "@/components/portal/motion/reveal-on-scroll";
import { SuggestionCard } from "@/components/portal/sections/suggestion-card";
import { useDailyReport, useLabRecommendations } from "@/lib/portal/hooks";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import type {
  MyLab,
  RecommendedMember,
  Suggestion,
} from "@/lib/portal/types";

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function SkeletonCard() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="h-6 w-6 rounded-full bg-surface-alt" />
          <span className="block h-4 w-48 rounded bg-surface-alt" />
        </div>
        <span className="h-5 w-20 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-2.5 w-32 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
      <span className="mt-1.5 block h-3 w-2/3 rounded bg-surface-alt" />
    </Card>
  );
}

/** How many papers Mylo ranks itself; the rest are cross-embedding matches. */
const PRIMARY_COUNT = 10;

/** How many papers each infinite-scroll slice reveals — one Mylo tier's worth,
 * so the first slice is exactly the LLM-ranked picks and the cross-topics tail
 * follows on its own as the reader keeps going. */
const PAPER_PAGE_SIZE = PRIMARY_COUNT;

/**
 * The Research Papers page: the top papers ranked and percent-matched by the
 * language model, with the remaining cross-embedding matches following in the
 * same scroll — the feed keeps loading as the reader goes rather than stopping
 * at a toggle. Above the list sit a keyword search and one row of
 * cluster chips — pick a research theme, or see everything. Fed by the same
 * daily run as the Daily Report summary.
 */
export function ResearchPapersSection() {
  const { currentLab } = usePortal();
  // In a lab workspace, this page is the lab's matched papers, not the caller's.
  if (currentLab) {
    return <LabPapersFeed lab={currentLab} />;
  }
  return <PersonalResearchPapers />;
}

/** The lab-scoped Research Papers feed — the lab's matches, same UI as personal. */
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
      matchThreshold={data?.summary?.match_threshold}
    />
  );
}

/**
 * Marks where Mylo's own ranked picks end and the cross-embedding tail begins.
 * The tail used to sit behind a "show more" button; now that it streams in with
 * the scroll, this rule is what keeps the two tiers legible.
 */
function CrossTopicsDivider() {
  return (
    <div className="flex items-center gap-3 pt-2">
      <span aria-hidden className="h-px flex-1 bg-border" />
      <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
        Cross-topics matches
      </span>
      <span aria-hidden className="h-px flex-1 bg-border" />
    </div>
  );
}

/**
 * The shared Research Papers feed body — keyword search, the cluster row, the
 * LLM-ranked / cross-topics two-tier split, and the infinite-scroll card list —
 * used identically by the personal page and a lab workspace. `labName`, when
 * set, marks the lab variant and only swaps the surrounding copy; the structure,
 * filters, and card layout are the same in both. `scanning` is a personal-only
 * sign-up state (a lab never passes it).
 */
function PapersFeed({
  suggestions,
  isLoading,
  isError,
  scanning = false,
  generatedAt = null,
  matchThreshold,
  recommendedFor,
  labName,
}: {
  suggestions: Suggestion[];
  isLoading: boolean;
  isError: boolean;
  scanning?: boolean;
  generatedAt?: string | null;
  matchThreshold?: number;
  /** Lab-only: content id → the members Mylo judges each paper is for. */
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
}) {
  const [selectedCluster, setSelectedCluster] = React.useState<string | null>(
    null,
  );
  const [query, setQuery] = React.useState("");

  const clusters = React.useMemo(
    () => clusterOptions(suggestions),
    [suggestions],
  );

  const searchActive = query.trim() !== "";
  const filtering = searchActive || selectedCluster !== null;

  // The filtered list, computed only when filtering is active. Search (title OR
  // abstract substring) and the selected cluster combine with AND. Papers keep
  // their own match percent throughout — the ring always shows the real score
  // rather than a number derived from whatever happens to be selected.
  const filtered: Suggestion[] = React.useMemo(() => {
    if (!filtering) return [];
    const needle = query.trim().toLowerCase();
    let rows = suggestions;
    if (needle) {
      rows = rows.filter(
        (s) =>
          s.title.toLowerCase().includes(needle) ||
          s.abstract.toLowerCase().includes(needle),
      );
    }
    if (selectedCluster) {
      rows = rows.filter((s) => s.cluster?.id === selectedCluster);
    }
    return rows;
  }, [filtering, query, selectedCluster, suggestions]);

  // One ordered list either way: the filtered results, or the full feed with the
  // LLM-ranked papers first and the cross-embedding tail behind them. The tail is
  // no longer gated behind a toggle — it simply keeps arriving as the reader
  // scrolls, with a divider marking where Mylo's own ranking ends.
  const feed = filtering ? filtered : suggestions;
  const rankedCount = Math.min(PRIMARY_COUNT, suggestions.length);
  const dividerAt = !filtering && suggestions.length > rankedCount ? rankedCount : -1;

  const { visible: displayed, hasMore, remaining, sentinelRef, revealMore } =
    useInfiniteReveal(feed, PAPER_PAGE_SIZE, `${query}|${selectedCluster ?? ""}`);

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering today's papers…";
    if (suggestions.length === 0) {
      return labName
        ? `Papers Mylo matched to ${labName}.`
        : "Your daily paper suggestions, ranked by how well they match your research.";
    }
    if (filtering) {
      const n = filtered.length;
      return `${n} paper${n === 1 ? "" : "s"} match your filters.`;
    }
    const when = formatWhen(generatedAt);
    const total = suggestions.length;
    const papers = `paper${total === 1 ? "" : "s"}`;
    const met = labName
      ? `${total} ${papers} Mylo matched to ${labName}`
      : typeof matchThreshold === "number"
        ? `${total} ${papers} met your ${matchThreshold}% match threshold`
        : `${total} ${papers} matched your research`;
    const ranked = `top ${rankedCount} ranked by Mylo`;
    return when
      ? `${met} — ${ranked} · gathered ${when}.`
      : `${met} — ${ranked}.`;
  })();

  return (
    <div>
      <SectionHeader
        eyebrow="Your feed"
        title="Research Papers"
        subtitle={subtitle}
      />

      {scanning ? (
        <div
          role="status"
          aria-live="polite"
          className="mb-5 flex items-center gap-3 rounded-xl border border-[color-mix(in_srgb,var(--primary)_30%,var(--border))] bg-[color-mix(in_srgb,var(--primary)_8%,transparent)] px-4 py-3 text-sm text-[var(--text-secondary)]"
        >
          <span className="h-2.5 w-2.5 flex-none rounded-full bg-brand-secondary motion-safe:animate-pulse" />
          Scanning new articles for you… fresh matches will appear here shortly.
        </div>
      ) : null}

      {suggestions.length > 0 ? (
        <FeedSearchBar
          query={query}
          onQueryChange={setQuery}
          placeholder="Search papers by title or abstract…"
          clusters={clusters}
          selectedCluster={selectedCluster}
          onClusterChange={setSelectedCluster}
        />
      ) : null}

      {isLoading ? (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<DocumentIcon size={28} />}
          title={
            labName
              ? "Couldn't load this feed"
              : "Couldn't load your research papers"
          }
          description={
            labName
              ? "Something went wrong loading the lab's paper matches. Please try again in a moment."
              : "Something went wrong fetching today's papers. Please try again in a moment."
          }
        />
      ) : suggestions.length === 0 ? (
        labName ? (
          <EmptyState
            icon={<DocumentIcon size={28} />}
            title="No lab paper matches yet"
            description="Once Mylo has run for this lab, papers matched to its shared research profile will appear here."
          />
        ) : scanning ? (
          <EmptyState
            icon={<DocumentIcon size={28} />}
            title="Scanning new articles for you…"
            description="Your watch topics didn't have enough fresh matches yet, so Mylo is searching new sources now. Your top papers will appear here in a moment."
          />
        ) : (
          <EmptyState
            icon={<DocumentIcon size={28} />}
            badge="Coming soon"
            title="Your first paper suggestions are on their way"
            description="Once Mylo's literature scan runs against your research profile, your top matching papers — each with a percent-match score and why-it-matters context — will appear here."
          />
        )
      ) : filtering && filtered.length === 0 ? (
        <EmptyState
          icon={<DocumentIcon size={28} />}
          title="No papers match your filters"
          description="Try picking a different cluster, or clearing the search to widen the results."
        />
      ) : (
        <>
          <div className="space-y-4">
            {displayed.map((suggestion, index) => (
              <React.Fragment key={suggestion.content_id}>
                {index === dividerAt ? <CrossTopicsDivider /> : null}
                <RevealOnScroll
                  delay={revealDelay(index, PAPER_PAGE_SIZE, 60)}
                >
                  <SuggestionCard
                    suggestion={suggestion}
                    recommendedFor={recommendedFor?.[suggestion.content_id]}
                    ignorable
                  />
                </RevealOnScroll>
              </React.Fragment>
            ))}
          </div>

          <FeedSentinel
            sentinelRef={sentinelRef}
            hasMore={hasMore}
            remaining={remaining}
            onRevealMore={revealMore}
            totalShown={displayed.length}
            noun="papers"
          />

          {!filtering ? (
            <p className="mt-5 text-xs text-[var(--text-secondary)]">
              The papers above the divider were ranked and percent-matched by
              the language model — the percent reflects how well it judges each
              paper fits your research. The cross-topics matches are the rest of
              the papers that cleared your match threshold, each showing its
              transformer (embedding-similarity) match percent, in
              recommendation order.
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
