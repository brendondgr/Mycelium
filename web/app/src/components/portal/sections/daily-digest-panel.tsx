"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  BellIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import { usePortal, type SectionKey } from "@/components/portal/portal-context";
import { useDailyReport, useProfile } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";

/** "Jun 29" style short date for the digest timestamp. */
function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * The Overview's right-rail notices panel: a calm synopsis of the user's daily
 * research report. When a digest has run it surfaces the top matches as alert
 * rows; otherwise it stays honest about the pending first scan and nudges any
 * setup that would sharpen results. Every line is grounded in real app state —
 * no fabricated counts. Pairs with the Mylo radar card on the left.
 */
export function DailyDigestPanel() {
  const { goToSection } = usePortal();
  const reportQuery = useDailyReport();
  const profileQuery = useProfile();

  const suggestions = reportQuery.data?.suggestions ?? [];
  const top = suggestions.slice(0, 3);
  const when = formatWhen(reportQuery.data?.generated_at ?? null);
  const completeness = computeCompleteness(profileQuery.data);
  const profileIncomplete =
    !profileQuery.isLoading && completeness.percent < 100;

  // Synopsis line — setup-aware, never fakes results.
  let synopsis: string;
  if (reportQuery.isLoading) {
    synopsis = "Gathering today's digest…";
  } else if (reportQuery.isError) {
    synopsis = "Couldn't load today's digest — try again shortly.";
  } else if (suggestions.length > 0) {
    const count = `${suggestions.length} paper${suggestions.length === 1 ? "" : "s"}`;
    synopsis = when
      ? `${count} matched your profile, gathered ${when}.`
      : `${count} matched your profile and are worth a look.`;
  } else {
    synopsis = "No new papers yet — Mylo is still scanning your topics.";
  }

  return (
    <Card className="flex h-full flex-col p-6">
      {/* Eyebrow */}
      <div className="mb-[9px] flex items-center gap-2">
        <BellIcon size={14} className="text-primary" aria-hidden="true" />
        <span className="text-[10.5px] font-semibold uppercase tracking-[.09em] text-primary">
          Daily report{when ? ` · ${when}` : ""}
        </span>
      </div>

      {/* Synopsis */}
      <p className="m-0 mb-4 text-[14.5px] leading-[1.5] text-[var(--text-secondary)] [text-wrap:pretty]">
        {synopsis}
      </p>

      {/* Notices */}
      <div className="flex flex-1 flex-col gap-2">
        {top.length > 0
          ? top.map((s) => {
              const isMylo = s.origin === "llm";
              return (
                <button
                  key={s.content_id}
                  type="button"
                  onClick={() => goToSection("daily" as SectionKey)}
                  className="group flex w-full items-start gap-2.5 rounded-xl border border-[var(--divider)] bg-surface-alt/40 px-3 py-2.5 text-left transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-[11px] font-semibold text-primary">
                    {s.rank ?? "·"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-[13px] font-medium leading-snug text-[var(--text-primary)]">
                      {s.headline}
                    </span>
                  </span>
                  <Pill tone={isMylo ? "accent" : "neutral"} className="shrink-0">
                    {isMylo ? (
                      <>
                        <SparkleIcon size={11} aria-hidden="true" />
                        Pick
                      </>
                    ) : (
                      "Match"
                    )}
                  </Pill>
                </button>
              );
            })
          : null}

        {/* Setup nudge shown when there's nothing to report yet. */}
        {top.length === 0 && profileIncomplete ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-dashed border-border px-3 py-2.5">
            <AlertTriangleIcon
              size={15}
              className="mt-0.5 shrink-0 text-[var(--accent)]"
              aria-hidden="true"
            />
            <p className="m-0 text-[12.5px] leading-snug text-[var(--text-secondary)]">
              Your profile is {completeness.percent}% complete — finishing it
              helps Mylo find sharper matches for tomorrow&apos;s digest.
            </p>
          </div>
        ) : null}

        {top.length === 0 && !profileIncomplete && !reportQuery.isLoading ? (
          <p className="m-0 text-[12.5px] leading-snug text-[var(--text-muted)]">
            Your morning digest will appear here as soon as the first scan runs.
          </p>
        ) : null}
      </div>

      {/* Footer link */}
      <button
        type="button"
        onClick={() => goToSection("daily" as SectionKey)}
        className="mt-4 inline-flex items-center gap-1.5 self-start text-[13px] font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
      >
        Open daily report
        <ArrowRightIcon size={14} aria-hidden="true" />
      </button>
    </Card>
  );
}
