"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { DocumentIcon, SearchIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { SuggestionCard } from "@/components/portal/sections/suggestion-card";
import { useDailyReport, useLabRecommendations } from "@/lib/portal/hooks";
import type { MyLab, Suggestion } from "@/lib/portal/types";

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

/** How many papers show by default; the rest are cross-embedding matches. */
const PRIMARY_COUNT = 10;

type ClusterOption = { id: string; label: string };

/** The distinct clusters attributed across today's papers, in the order they
 * first appear — the source of the cluster filter row. A profile whose papers
 * carry no cluster at all yields an empty list and the row stays hidden. */
function clusterSet(suggestions: Suggestion[]): ClusterOption[] {
  const seen = new Map<string, string>();
  for (const s of suggestions) {
    if (s.cluster && !seen.has(s.cluster.id)) {
      seen.set(s.cluster.id, s.cluster.label);
    }
  }
  return Array.from(seen, ([id, label]) => ({ id, label }));
}

/**
 * The Research Papers page: the top papers ranked and percent-matched by the
 * language model, with the remaining cross-embedding matches tucked behind a
 * "show more" toggle. Above the list sit a keyword search and one row of
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
 * The shared Research Papers feed body — keyword search, the cluster row, the
 * LLM-ranked / cross-topics two-tier split, and the card list —
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
  labName,
}: {
  suggestions: Suggestion[];
  isLoading: boolean;
  isError: boolean;
  scanning?: boolean;
  generatedAt?: string | null;
  matchThreshold?: number;
  labName?: string;
}) {
  const [showMore, setShowMore] = React.useState(false);
  const [selectedCluster, setSelectedCluster] = React.useState<string | null>(
    null,
  );
  const [query, setQuery] = React.useState("");

  const clusters = React.useMemo(() => clusterSet(suggestions), [suggestions]);
  const showClusterTier = clusters.length >= 1;

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

  // The default two-tier split (no filtering): LLM-ranked papers, then the
  // cross-embedding tail behind a toggle.
  const primary = suggestions.slice(0, PRIMARY_COUNT);
  const extra = suggestions.slice(PRIMARY_COUNT);

  /** Selecting a cluster narrows the feed to it; re-selecting clears. */
  const toggleCluster = (clusterId: string) => {
    setSelectedCluster((prev) => (prev === clusterId ? null : clusterId));
  };

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
    const ranked = `top ${primary.length} ranked by Mylo`;
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
        <div className="mb-5 space-y-3">
          <label className="relative block">
            <span className="sr-only">Search papers by title or abstract</span>
            <SearchIcon
              size={16}
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)]"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search papers by title or abstract…"
              className="w-full rounded-full border border-[var(--border)] bg-[var(--surface)] py-2 pl-9 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[color-mix(in_srgb,var(--primary)_45%,var(--border))] focus:outline-none"
            />
          </label>

          {/* Clusters, and only clusters. The per-interest chip tier that used
              to sit under this row restated what the cluster already says and
              crowded the top of the page, so the rail stays one line: pick a
              theme, or see everything. */}
          {showClusterTier ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
                Clusters
              </span>
              <button
                type="button"
                onClick={() => setSelectedCluster(null)}
                aria-pressed={selectedCluster === null}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  selectedCluster === null
                    ? "border-[color-mix(in_srgb,var(--primary)_45%,transparent)] bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] text-primary"
                    : "border-[var(--border)] bg-[var(--surface-alt)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                All
              </button>
              {clusters.map((cluster) => {
                const on = selectedCluster === cluster.id;
                const token = clusterAccentVar(cluster.id);
                return (
                  <button
                    key={cluster.id}
                    type="button"
                    onClick={() => toggleCluster(cluster.id)}
                    aria-pressed={on}
                    className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors"
                    style={
                      on
                        ? {
                            borderColor: `color-mix(in srgb, var(${token}) 45%, transparent)`,
                            backgroundColor: `color-mix(in srgb, var(${token}) 14%, transparent)`,
                            color: `var(${token})`,
                          }
                        : {
                            borderColor: "var(--border)",
                            backgroundColor: "var(--surface-alt)",
                            color: "var(--text-secondary)",
                          }
                    }
                  >
                    <span
                      aria-hidden="true"
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: `var(${token})` }}
                    />
                    {cluster.label}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
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
      ) : filtering ? (
        filtered.length === 0 ? (
          <EmptyState
            icon={<DocumentIcon size={28} />}
            title="No papers match your filters"
            description="Try picking a different cluster, or clearing the search to widen the results."
          />
        ) : (
          <div className="space-y-4">
            {filtered.map((suggestion, index) => (
              <div
                key={suggestion.content_id}
                className="portal-fade-up"
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <SuggestionCard suggestion={suggestion} />
              </div>
            ))}
          </div>
        )
      ) : (
        <>
          <div className="space-y-4">
            {primary.map((suggestion, index) => (
              <div
                key={suggestion.content_id}
                className="portal-fade-up"
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <SuggestionCard suggestion={suggestion} />
              </div>
            ))}
          </div>

          {extra.length > 0 ? (
            <div className="mt-4">
              <button
                type="button"
                onClick={() => setShowMore((open) => !open)}
                aria-expanded={showMore}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
              >
                {showMore
                  ? "Hide cross-topics matches"
                  : `Show ${extra.length} more cross-topics match${
                      extra.length === 1 ? "" : "es"
                    }`}
              </button>

              {showMore ? (
                <div className="mt-4 space-y-4">
                  {extra.map((suggestion, index) => (
                    <div
                      key={suggestion.content_id}
                      className="portal-fade-up"
                      style={{ animationDelay: `${index * 60}ms` }}
                    >
                      <SuggestionCard suggestion={suggestion} />
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <p className="mt-5 text-xs text-[var(--text-secondary)]">
            The top papers marked “Mylo pick” were ranked and percent-matched by
            the language model — the percent reflects how well it judges each
            paper fits your research. The cross-topics matches are the rest of
            the papers that cleared your match threshold, each showing its
            transformer (embedding-similarity) match percent, in recommendation
            order.
          </p>
        </>
      )}
    </div>
  );
}
