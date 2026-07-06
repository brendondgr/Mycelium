"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ArrowRightIcon, SparkleIcon } from "@/components/portal/icons";
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

/** A paper at or above this percent match is highlighted as a strong fit. */
const STRONG_MATCH = 75;

/**
 * The model's percent match for this researcher. Text always carries the value
 * ("87% match" / "Strong"), so color is never the only signal; the accent tone
 * only reinforces a strong fit.
 */
function MatchBadge({ percent }: { percent: number }) {
  const strong = percent >= STRONG_MATCH;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold"
      style={
        strong
          ? {
              borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
              backgroundColor: "color-mix(in srgb, var(--accent) 14%, transparent)",
              color: "var(--accent)",
            }
          : {
              borderColor: "var(--border)",
              backgroundColor: "var(--surface-alt)",
              color: "var(--text-secondary)",
            }
      }
      aria-label={`${percent} percent match to your research profile${
        strong ? ", a strong match" : ""
      }`}
    >
      <span aria-hidden="true">{percent}%</span>
      <span className="text-[var(--text-muted)]">match</span>
    </span>
  );
}

/**
 * One research-article suggestion: rank, headline, why-it-matters reason, and a
 * link to the source. The gold "Mylo pick" chip marks a language-model reason;
 * a neutral chip marks a templated topical match — color is never the only
 * signal, the chip always carries text. Lifts gently on hover (reduced-motion
 * aware via the global transition).
 */
export function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
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
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {typeof suggestion.match_percent === "number" ? (
            <MatchBadge percent={suggestion.match_percent} />
          ) : null}
          <Pill tone={isMylo ? "accent" : "neutral"} className="shrink-0">
            {isMylo ? (
              <>
                <SparkleIcon size={12} aria-hidden="true" />
                Mylo pick
              </>
            ) : (
              "Cross-embedding match"
            )}
          </Pill>
        </div>
      </div>

      <p className="mt-1.5 text-xs text-[var(--text-muted)]">
        {metaLine(suggestion)}
      </p>

      <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
        {suggestion.reason}
      </p>

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
