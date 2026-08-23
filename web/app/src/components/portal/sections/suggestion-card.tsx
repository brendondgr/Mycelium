"use client";

import * as React from "react";

import { MatchCard } from "@/components/portal/primitives/match-card";
import { PositionMark, VerdictBadge } from "@/components/portal/primitives/verdict-badge";
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
 * the feed is Mylo's own ranking, which the verdict chip already attributes with
 * his portrait, so labelling it again on every row said nothing. Lifts gently on
 * hover (reduced-motion aware via the global transition).
 *
 * Laid out by `MatchCard`: the item's place in its theme and Mylo's verdict sit
 * in a notch at the top-left beside the badges, title and meta line; the
 * abstract, the full reason, the caveat and the link run the card's full width
 * beneath it.
 *
 * **This is where the reasoning lives.** The printed report carries only the
 * reason's first beat, because a morning brief is a record of what arrived; the
 * remaining beats and the caveat are here, on demand, where a reader who wants
 * depth has asked for it. The caveat is the part that makes the card read as
 * judgement rather than promotion, so it is never hidden behind a disclosure.
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
      ring={
        <div className="flex w-16 shrink-0 flex-col items-center gap-1.5">
          <PositionMark
            position={suggestion.position}
            theme={suggestion.cluster?.label}
          />
          <VerdictBadge verdict={suggestion.verdict} origin={suggestion.origin} />
        </div>
      }
      head={
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {/* The title is always the first line, so it lines up with the top
                of the gutter on every card. Anything optional (cluster chips)
                goes below it, where its absence cannot shift the title.

                The position is *not* repeated here. It lives in the gutter, and
                printing the same number twice on one card invited the reader to
                look for a difference between them. */}
            <div className="flex min-w-0 items-start gap-3">
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

      {/* The strongest reason to skip it. Printed plainly rather than tucked
          away: a recommendation with no stated downside is an advertisement. */}
      {suggestion.caveat ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">
          <span className="font-semibold">Worth knowing: </span>
          {suggestion.caveat}
        </p>
      ) : null}

      {suggestion.bridge_note ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          {suggestion.bridge_note}
        </p>
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
