"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
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
import type { Suggestion } from "@/lib/portal/types";

function metaLine(suggestion: Suggestion): string {
  const parts: string[] = [suggestion.source];
  if (suggestion.venue) parts.push(suggestion.venue);
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
 * Layout is a left gutter holding the match ring, with the card's content stack
 * beside it. The ring shows the language model's own percent and, when Mylo
 * authored the judgement, his portrait as attribution; the cross-embedding tail
 * (no model percent) falls back to its transformer `embedding_match`. Every
 * feed card in the workspace shares this shape.
 */
export function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  const isMylo = suggestion.origin === "llm";

  return (
    <Card className="p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex gap-4 sm:gap-5">
        {/* Left gutter: how well this fits, before anything else is read. */}
        <MatchRing
          percent={suggestion.match_percent ?? suggestion.embedding_match}
          origin={suggestion.origin}
          className="mt-0.5 hidden sm:flex"
        />

        <div className="min-w-0 flex-1">
          {/* Top row: the ring's mobile stand-in and cluster attribution lead;
              status + actions trail on the right. */}
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <MatchRing
                percent={suggestion.match_percent ?? suggestion.embedding_match}
                origin={suggestion.origin}
                size="sm"
                className="sm:hidden"
              />
              {suggestion.cluster ? (
                <ClusterBadge cluster={suggestion.cluster} />
              ) : null}
              {suggestion.bridge_clusters?.length ? (
                <BridgeBadge clusters={suggestion.bridge_clusters} />
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

          <div className="mt-2.5 flex min-w-0 items-start gap-3">
            {suggestion.rank ? (
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-xs font-semibold text-primary">
                {suggestion.rank}
              </span>
            ) : null}
            <h3 className="min-w-0 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
              {suggestion.headline}
            </h3>
          </div>

          <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
            {metaLine(suggestion)}
          </p>

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
        </div>
      </div>
    </Card>
  );
}
