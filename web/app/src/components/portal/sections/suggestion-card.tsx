"use client";

import * as React from "react";

import { MatchCard } from "@/components/portal/primitives/match-card";
import { MatchRing } from "@/components/portal/primitives/match-ring";
import { Pill } from "@/components/portal/primitives/pill";
import {
  BridgeBadge,
  ClusterBadge,
} from "@/components/portal/primitives/cluster-badge";
import {
  MyloReason,
  NewTag,
  IgnoreButton,
  IgnoredStrip,
  SaveButton,
} from "@/components/portal/sections/opportunity-bits";
import { ArrowRightIcon } from "@/components/portal/icons";
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
 * link to the source. Only the cross-topics tail carries a chip — the rest of
 * the feed is Mylo's own ranking, which the ring already attributes with his
 * portrait, so labelling it again on every row said nothing. Lifts gently on
 * hover (reduced-motion aware via the global transition).
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
  ignorable = false,
}: {
  suggestion: Suggestion;
  recommendedFor?: RecommendedMember[];
  /**
   * Show the ignore control. Feeds pass it; the Saves page does not — a save is
   * this reader asking to keep the item, so offering to hide it there would be
   * two controls arguing about the same row.
   */
  ignorable?: boolean;
}) {
  const [ignored, setIgnored] = React.useState(false);
  const isMylo = suggestion.origin === "llm";
  const percent = suggestion.match_percent ?? suggestion.embedding_match;
  const provenance = provenanceLine(suggestion);
  const byline = bylineLine(suggestion);

  // Ignored: collapse in place rather than leaving a gap, so the reader can see
  // what happened and undo a misfire before the next refetch drops the row.
  if (ignored) {
    return (
      <IgnoredStrip
        contentId={suggestion.content_id}
        title={suggestion.title}
        onRestored={() => setIgnored(false)}
      />
    );
  }

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
            {/* Only the cross-topics tail is labelled. Every other row in this
                feed is a Mylo pick, and a chip that appears on nearly all of
                them distinguishes nothing — the ring already carries his
                portrait when he made the judgement. */}
            {isMylo ? null : (
              <Pill tone="neutral" className="shrink-0">
                Cross-topics match
              </Pill>
            )}
            <SaveButton
              contentId={suggestion.content_id}
              saved={suggestion.saved}
              savedLabs={suggestion.saved_labs}
              variant="icon"
            />
            {ignorable ? (
              <IgnoreButton
                contentId={suggestion.content_id}
                title={suggestion.title}
                onIgnored={() => setIgnored(true)}
              />
            ) : null}
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
