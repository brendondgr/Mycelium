"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { DocumentIcon } from "@/components/portal/icons";
import { SuggestionCard } from "@/components/portal/sections/suggestion-card";
import { useDailyReport } from "@/lib/portal/hooks";

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

/**
 * The Research Papers page: the top papers ranked and percent-matched by the
 * language model, with the remaining cross-embedding matches tucked behind a
 * "show more" toggle (ranked by recommendation, no model percent). Fed by the
 * same daily run as the Daily Report summary.
 */
export function ResearchPapersSection() {
  const { data, isLoading, isError } = useDailyReport();
  const suggestions = data?.suggestions ?? [];
  const [showMore, setShowMore] = React.useState(false);

  // The first PRIMARY_COUNT are the language-model-ranked papers (each with a
  // percent match); the rest are the cross-embedding tail, in recommendation
  // order, revealed on demand.
  const primary = suggestions.slice(0, PRIMARY_COUNT);
  const extra = suggestions.slice(PRIMARY_COUNT);

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering today's papers…";
    if (suggestions.length > 0) {
      const when = formatWhen(data?.generated_at ?? null);
      const count = `Top ${primary.length} paper${primary.length === 1 ? "" : "s"}`;
      const more = extra.length > 0 ? ` · ${extra.length} more matches` : "";
      return when
        ? `${count}, ranked by Mylo${more} · gathered ${when}.`
        : `${count}, ranked by Mylo${more}.`;
    }
    return "Your daily paper suggestions, ranked by how well they match your research.";
  })();

  return (
    <div>
      <SectionHeader title="Research Papers" subtitle={subtitle} />

      {isLoading ? (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<DocumentIcon size={28} />}
          title="Couldn't load your research papers"
          description="Something went wrong fetching today's papers. Please try again in a moment."
        />
      ) : suggestions.length === 0 ? (
        <EmptyState
          icon={<DocumentIcon size={28} />}
          badge="Coming soon"
          title="Your first paper suggestions are on their way"
          description="Once Milo's literature scan runs against your research profile, your top matching papers — each with a percent-match score and why-it-matters context — will appear here."
        />
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
                  ? "Hide cross-embedding matches"
                  : `Show ${extra.length} more cross-embedding match${
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

          <p className="mt-5 text-xs text-[var(--text-muted)]">
            The top papers marked “Mylo pick” were ranked and percent-matched by the
            language model — the percent reflects how well it judges each paper fits
            your research. The cross-embedding matches are further papers found by
            embedding similarity, listed in recommendation order (no model percent).
          </p>
        </>
      )}
    </div>
  );
}
