"use client";

import { LinesSkeleton } from "@/components/portal/skeleton";
import { usePortal } from "@/components/portal/portal-context";
import { ArrowRightIcon, CalendarIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import type { SavedDeadline } from "@/lib/portal/types";

/**
 * The overview's saved-deadlines panel, fed by props so it stays free of any
 * scope-specific data fetching. The rest of the overview lives in
 * `overview-layout.tsx`.
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
        <LinesSkeleton rows={2} />
      ) : items.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
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
