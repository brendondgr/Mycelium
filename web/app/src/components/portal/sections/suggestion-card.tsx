"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ArrowRightIcon, SparkleIcon } from "@/components/portal/icons";
import {
  MatchBadge,
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
 * One research-article suggestion: rank, headline, why-it-matters reason, and a
 * link to the source. The gold "Mylo pick" chip marks a language-model reason;
 * a neutral chip marks a templated topical match — color is never the only
 * signal, the chip always carries text. Lifts gently on hover (reduced-motion
 * aware via the global transition).
 *
 * When the reader is filtering by interest (`focusMode`), the badge shows a
 * `displayPercent` derived from that paper's per-interest fusion scores with a
 * neutral dot — that number is not Mylo's holistic judgement, so it never wears
 * the headshot. Unfiltered, the badge shows the language model's own percent and
 * (when Mylo authored it) its headshot, matching the Grants page; the
 * cross-embedding tail (no model percent) falls back to its transformer
 * `embedding_match` with a neutral dot.
 */
export function SuggestionCard({
  suggestion,
  displayPercent,
  focusMode = false,
}: {
  suggestion: Suggestion;
  displayPercent?: number;
  focusMode?: boolean;
}) {
  const isMylo = suggestion.origin === "llm";

  return (
    <Card className="p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex items-start justify-between gap-3">
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
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {suggestion.is_new ? <NewTag /> : null}
          {focusMode ? (
            <MatchBadge percent={displayPercent ?? null} />
          ) : (
            <MatchBadge
              percent={suggestion.match_percent ?? suggestion.embedding_match}
              origin={suggestion.origin}
            />
          )}
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
            variant="icon"
          />
        </div>
      </div>

      <p className="mt-1.5 text-xs text-[var(--text-muted)]">
        {metaLine(suggestion)}
      </p>

      {suggestion.abstract ? (
        <p className="mt-3 line-clamp-5 text-sm leading-relaxed text-[var(--text-secondary)]">
          {suggestion.abstract}
        </p>
      ) : null}

      {/* Mylo's read on why this fits — a soft primary field flags the AI note,
          matching the Grants page. A templated topical match stays a plain line. */}
      {suggestion.reason ? (
        isMylo ? (
          <div
            className="mt-3 flex items-start gap-2.5 rounded-xl border p-3"
            style={{
              borderColor: "color-mix(in srgb, var(--primary) 30%, transparent)",
              backgroundColor: "color-mix(in srgb, var(--primary) 8%, transparent)",
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/mylo-headshot.webp"
              alt=""
              width={24}
              height={24}
              className="mt-0.5 h-6 w-6 shrink-0 rounded-full object-cover"
            />
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
              {suggestion.reason}
            </p>
          </div>
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
    </Card>
  );
}
