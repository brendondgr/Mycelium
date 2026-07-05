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

/**
 * The Research Papers page: today's ranked paper suggestions, each with a
 * percent-match badge and a why-it-matters reason. Fed by the same daily run as
 * the Daily Report summary, but this is where the individual papers live.
 */
export function ResearchPapersSection() {
  const { data, isLoading, isError } = useDailyReport();
  const suggestions = data?.suggestions ?? [];
  // The top tier is ranked and explained by the language model ("Mylo pick"); the
  // rest are surfaced by the fusion scoring with deterministic reasons. The tail
  // begins where the LLM-ranked cards end.
  const llmCount = suggestions.filter((s) => s.origin === "llm").length;
  const hasTail = llmCount > 0 && llmCount < suggestions.length;

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering today's papers…";
    if (suggestions.length > 0) {
      const when = formatWhen(data?.generated_at ?? null);
      const count = `Top ${suggestions.length} paper${
        suggestions.length === 1 ? "" : "s"
      }`;
      const ranked = llmCount > 0 ? `, top ${llmCount} ranked by Mylo` : "";
      return when
        ? `${count}${ranked} · gathered ${when}.`
        : `${count}, ranked by match to your research.`;
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
            {suggestions.map((suggestion, index) => (
              <React.Fragment key={suggestion.content_id}>
                {hasTail && index === llmCount ? (
                  <div
                    className="flex items-center gap-3 pt-2 text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]"
                    role="separator"
                  >
                    <span className="h-px flex-1 bg-[var(--border)]" />
                    Also surfaced
                    <span className="h-px flex-1 bg-[var(--border)]" />
                  </div>
                ) : null}
                <div
                  className="portal-fade-up"
                  style={{ animationDelay: `${index * 60}ms` }}
                >
                  <SuggestionCard suggestion={suggestion} />
                </div>
              </React.Fragment>
            ))}
          </div>
          <p className="mt-5 text-xs text-[var(--text-muted)]">
            Ranked from your research profile by Milo. The match score reflects how
            well each paper fits your interests. The top papers marked “Mylo pick”
            were ranked and explained by the language model; those under “Also
            surfaced” are further matches scored by topic and interest overlap.
          </p>
        </>
      )}
    </div>
  );
}
