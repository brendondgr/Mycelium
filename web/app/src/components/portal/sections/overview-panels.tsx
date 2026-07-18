"use client";

import { usePortal } from "@/components/portal/portal-context";
import { ArrowRightIcon, CalendarIcon, DocumentIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import { MatchBadge } from "@/components/portal/sections/opportunity-bits";
import type { SavedDeadline, Suggestion } from "@/lib/portal/types";

/**
 * The Overview's right-column panels — top papers and nearest deadlines — shared
 * by the personal and lab overviews so both render identically. Each is fed by
 * props (the personal daily report / saved deadlines, or a lab's recommendations
 * / shared saves), keeping them free of any scope-specific data fetching. They
 * live in their own module to avoid an import cycle between the two overviews.
 */

/** Small panel header with a "view all" affordance to the full section. */
function PanelHeader({ title, onView }: { title: string; onView: () => void }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="font-serif text-lg font-semibold text-[var(--text-primary)]">
        {title}
      </h2>
      <button
        type="button"
        onClick={onView}
        className="group inline-flex items-center gap-1 text-[13px] font-semibold text-primary hover:underline"
      >
        View all
        <ArrowRightIcon
          size={12}
          aria-hidden="true"
          className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
        />
      </button>
    </div>
  );
}

/** The Overview's right column, top: the top three daily papers + %. */
export function TopPapersPanel({
  suggestions,
  isLoading,
}: {
  suggestions: Suggestion[];
  isLoading: boolean;
}) {
  const { goToSection } = usePortal();
  const top = suggestions.slice(0, 3);

  return (
    <Card className="p-5">
      <PanelHeader title="Research Papers" onView={() => goToSection("papers")} />
      {isLoading ? (
        <p className="text-sm text-[var(--text-muted)]">
          Gathering today&apos;s papers…
        </p>
      ) : top.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <DocumentIcon size={16} />
          Your first paper matches will appear here after tonight&apos;s scan.
        </div>
      ) : (
        <ul className="space-y-3">
          {top.map((paper) => (
            <li
              key={paper.content_id}
              className="flex items-start justify-between gap-3"
            >
              <div className="flex min-w-0 items-start gap-2.5">
                {paper.rank ? (
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-[11px] font-semibold text-primary">
                    {paper.rank}
                  </span>
                ) : null}
                <span className="min-w-0 text-sm font-medium leading-snug text-[var(--text-primary)]">
                  {paper.headline || paper.title}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {paper.cluster ? (
                  <>
                    <span
                      aria-hidden="true"
                      title={paper.cluster.label}
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{
                        backgroundColor: `var(${clusterAccentVar(paper.cluster.id)})`,
                      }}
                    />
                    <span className="sr-only">{paper.cluster.label} cluster</span>
                  </>
                ) : null}
                <MatchBadge percent={paper.match_percent} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The Overview's right column, below papers: the soonest saved deadlines. */
export function DeadlinesPanel({
  items: allItems,
  isLoading,
}: {
  items: SavedDeadline[];
  isLoading: boolean;
}) {
  const { goToSection } = usePortal();
  // Saves now include papers, which carry no deadline — only dated saves here.
  const items = allItems
    .filter((item) => item.deadline_date !== null)
    .slice(0, 4);

  return (
    <Card className="p-5">
      <PanelHeader title="Deadlines" onView={() => goToSection("saves")} />
      {isLoading ? (
        <p className="text-sm text-[var(--text-muted)]">Loading your deadlines…</p>
      ) : items.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <CalendarIcon size={16} />
          Save a grant or conference to start tracking its deadline here.
        </div>
      ) : (
        <ul className="space-y-2.5">
          {items.map((item) => {
            const days = item.days_remaining;
            const label =
              days === null
                ? ""
                : days < 0
                  ? "Passed"
                  : days === 0
                    ? "Due today"
                    : `${days}d left`;
            return (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="min-w-0 truncate text-[var(--text-primary)]">
                  {item.title}
                </span>
                <span
                  className="shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold"
                  style={{
                    borderColor: item.within_week
                      ? "color-mix(in srgb, var(--accent) 45%, transparent)"
                      : "var(--border)",
                    color: item.within_week
                      ? "var(--accent)"
                      : "var(--text-secondary)",
                  }}
                >
                  {label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
