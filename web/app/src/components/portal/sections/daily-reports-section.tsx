"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { ReportIcon } from "@/components/portal/icons";
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

export function DailyReportsSection() {
  const { data, isLoading, isError } = useDailyReport();
  const suggestions = data?.suggestions ?? [];

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering your digest…";
    if (suggestions.length > 0) {
      const when = formatWhen(data?.generated_at ?? null);
      const count = `${suggestions.length} paper${
        suggestions.length === 1 ? "" : "s"
      }`;
      return when ? `${count} · gathered ${when}.` : `${count} worth your attention.`;
    }
    return "Your personalized research digest, gathered every morning.";
  })();

  return (
    <div>
      <SectionHeader title="Daily Reports" subtitle={subtitle} />

      {isLoading ? (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          title="Couldn't load your daily report"
          description="Something went wrong fetching your digest. Please try again in a moment."
        />
      ) : suggestions.length === 0 ? (
        <EmptyState
          icon={<ReportIcon size={28} />}
          badge="Coming soon"
          title="Your first daily report is on its way"
          description="Once Milo's literature scan runs against your research profile, your morning digest — new papers with clear why-it-matters context — will appear here."
        />
      ) : (
        <>
          <div className="space-y-4">
            {suggestions.map((suggestion, index) => (
              <div
                key={suggestion.content_id}
                className="portal-fade-up"
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <SuggestionCard suggestion={suggestion} />
              </div>
            ))}
          </div>
          <p className="mt-5 text-xs text-[var(--text-muted)]">
            Picked from your research profile by Milo. Reasons marked “Mylo pick”
            were written by the language model; others are topical matches.
          </p>
        </>
      )}
    </div>
  );
}
