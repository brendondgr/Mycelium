"use client";

import * as React from "react";

import { MatchCard } from "@/components/portal/primitives/match-card";
import { MatchRing } from "@/components/portal/primitives/match-ring";
import { Pill } from "@/components/portal/primitives/pill";
import {
  BridgeBadge,
  ClusterBadge,
} from "@/components/portal/primitives/cluster-badge";
import { ArrowRightIcon, SparkleIcon } from "@/components/portal/icons";
import {
  MyloReason,
  NewTag,
  SaveButton,
} from "@/components/portal/sections/opportunity-bits";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import type { RecommendedMember, Suggestion } from "@/lib/portal/types";

/** Where we found it, and where it was published — one line. */
function provenanceLine(suggestion: Suggestion): string {
  return [suggestion.source, suggestion.venue].filter(Boolean).join(" · ");
}

/** When, and by whom — the line below. Split from the provenance so neither
 * has to wrap in the narrow column beside the ring. */
function bylineLine(suggestion: Suggestion): string {
  const parts: string[] = [];
  if (suggestion.year) parts.push(String(suggestion.year));
  if (suggestion.authors.length > 0) {
    parts.push(
      suggestion.authors.length > 1
        ? `${suggestion.authors[0]} et al.`
        : suggestion.authors[0],
    );
  }
  return parts.join(" · ");
}

/**
 * One research-article suggestion: fit, headline, why-it-matters reason, and a
 * link to the source. The gold "Mylo pick" chip marks a language-model reason;
 * a neutral chip marks a templated topical match — color is never the only
 * signal, the chip always carries text. Lifts gently on hover (reduced-motion
 * aware via the global transition).
 *
 * Laid out by `MatchCard`: the ring sits in a notch at the top-left beside the
 * badges, title and meta line, and the abstract, reason and link run the card's
 * full width beneath it. The ring shows the language model's own percent and,
 * when Mylo authored the judgement, his portrait as attribution; the
 * cross-embedding tail (no model percent) falls back to its transformer
 * `embedding_match`. Every scored feed card in the workspace shares this shape.
 *
 * `recommendedFor` is the lab-only "who is this for?" strip. A personal feed
 * never passes it and renders exactly as before.
 */
export function SuggestionCard({
  suggestion,
  recommendedFor,
}: {
  suggestion: Suggestion;
  recommendedFor?: RecommendedMember[];
}) {
  const isMylo = suggestion.origin === "llm";
  const percent = suggestion.match_percent ?? suggestion.embedding_match;
  const provenance = provenanceLine(suggestion);
  const byline = bylineLine(suggestion);

  return (
    <MatchCard
      ring={<MatchRing percent={percent} origin={suggestion.origin} />}
      head={
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {/* The title is always the first line, so it lines up with the top
                of the ring on every card. Anything optional (cluster chips)
                goes below it, where its absence cannot shift the title. */}
            <div className="flex min-w-0 items-start gap-3">
              {suggestion.rank ? (
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-xs font-semibold text-primary">
                  {suggestion.rank}
                </span>
              ) : null}
              <h3 className="min-w-0 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
                {suggestion.headline}
              </h3>
            </div>

            {/* Two fixed lines: where it came from, then when and by whom.
                Each clamps to one line so a long venue or author list can
                never push the card out of step with its neighbours. */}
            <p
              className="mt-1.5 line-clamp-1 text-xs text-[var(--text-secondary)]"
              title={provenance}
            >
              {provenance}
            </p>
            {byline ? (
              <p
                className="mt-0.5 line-clamp-1 text-xs text-[var(--text-secondary)]"
                title={byline}
              >
                {byline}
              </p>
            ) : null}

            {suggestion.cluster || suggestion.bridge_clusters?.length ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {suggestion.cluster ? (
                  <ClusterBadge cluster={suggestion.cluster} />
                ) : null}
                {suggestion.bridge_clusters?.length ? (
                  <BridgeBadge clusters={suggestion.bridge_clusters} />
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {suggestion.is_new ? <NewTag /> : null}
            <Pill tone={isMylo ? "accent" : "neutral"} className="shrink-0">
              {isMylo ? (
                <>
                  <SparkleIcon size={12} aria-hidden="true" />
                  Mylo pick
                </>
              ) : (
                "Cross-topics match"
              )}
            </Pill>
            <SaveButton
              contentId={suggestion.content_id}
              saved={suggestion.saved}
              savedLabs={suggestion.saved_labs}
              variant="icon"
            />
          </div>
        </div>
      }
    >
      {suggestion.abstract ? (
        <p className="mt-3 line-clamp-5 text-sm leading-relaxed text-[var(--text-secondary)]">
          {suggestion.abstract}
        </p>
      ) : null}

      {/* Mylo's read on why this fits — a soft primary field flags the AI
          note. A templated topical match stays a plain line. */}
      {suggestion.reason ? (
        isMylo ? (
          <MyloReason reason={suggestion.reason} />
        ) : (
          <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
            {suggestion.reason}
          </p>
        )
      ) : null}

      <RecommendedFor members={recommendedFor} />

      {suggestion.url ? (
        <a
          href={suggestion.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-3.5 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          Read paper
          <ArrowRightIcon
            size={14}
            aria-hidden="true"
            className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
          />
        </a>
      ) : null}
    </MatchCard>
  );
}
