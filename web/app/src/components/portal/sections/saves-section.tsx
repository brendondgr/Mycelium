"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  BankIcon,
  BellIcon,
  BookmarkIcon,
  ConferenceIcon,
  DocumentIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import { ReminderComposer } from "@/components/portal/reminder-composer";
import { deadlineLabel } from "@/components/portal/sections/opportunity-bits";
import { GrantRow } from "@/components/portal/sections/opportunities-section";
import { FellowshipRow } from "@/components/portal/sections/fellowships-section";
import { ConferenceCard } from "@/components/portal/sections/conferences-section";
import { SuggestionCard } from "@/components/portal/sections/suggestion-card";
import {
  AREA_LABELS,
  DEFAULT_SAVES_FILTERS,
  SavesFilters,
  deriveSavesFilterOptions,
  filterAndSortSaves,
  type SavesFilterState,
} from "@/components/portal/sections/saves-filters";
import { useSaves } from "@/lib/portal/hooks";
import type { DeadlineOption, SavedArea, SavedItem } from "@/lib/portal/types";

/** The addressable, *dated* deadlines a save can be reminded on ([] for papers). */
function reminderDeadlines(item: SavedItem): DeadlineOption[] {
  if (item.area === "paper") return [];
  if (item.card) return item.card.addressable_deadlines ?? [];
  // Pruned listing: fall back to the save's own snapshot deadline.
  if (item.deadline_date) {
    return [
      {
        kind: item.deadline_kind || "other",
        due_date: item.deadline_date,
        confidence: "confirmed",
        label: "",
      },
    ];
  }
  return [];
}

const AREA_ICONS: Record<SavedArea, React.ComponentType<{ size?: number }>> = {
  paper: DocumentIcon,
  grant: BankIcon,
  fellowship: SparkleIcon,
  conference: ConferenceIcon,
};

/** Format an ISO timestamp as "Jul 6, 2026" (the saved-on date). */
function formatDate(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function countdownLabel(days: number | null): string {
  if (days === null) return "";
  if (days < 0) return "Deadline passed";
  if (days === 0) return "Due today";
  return `${days} day${days === 1 ? "" : "s"} left`;
}

/**
 * The small meta strip above each saved card: what kind of item this is, when
 * it was saved, the countdown when a deadline is near, and the user's note.
 */
function SaveMeta({
  item,
  onRemind,
}: {
  item: SavedItem;
  onRemind?: () => void;
}) {
  const AreaIcon = AREA_ICONS[item.area];
  const savedOn = formatDate(item.saved_at);
  const countdown = countdownLabel(item.days_remaining);

  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 px-1">
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-secondary)]">
        <AreaIcon size={13} aria-hidden="true" />
        {AREA_LABELS[item.area].replace(/s$/, "")}
      </span>
      {savedOn ? (
        <span className="text-xs text-[var(--text-muted)]">Saved {savedOn}</span>
      ) : null}
      {countdown && item.within_week ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-[color-mix(in_srgb,var(--accent)_45%,transparent)] px-2 py-0.5 text-xs font-semibold text-accent">
          <AlertTriangleIcon size={11} aria-hidden="true" />
          {countdown}
        </span>
      ) : null}
      {item.note ? (
        <span className="min-w-0 truncate text-xs italic text-[var(--text-muted)]">
          Note: {item.note}
        </span>
      ) : null}
      {onRemind ? (
        <button
          type="button"
          onClick={onRemind}
          className="ml-auto inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <BellIcon size={11} aria-hidden="true" />
          Remind me
        </button>
      ) : null}
    </div>
  );
}

/**
 * The fallback row for a save whose source listing was pruned from the corpus:
 * the snapshot (title, subtitle, deadline) is all that remains, so it renders
 * as a compact card instead of the full feed layout.
 */
function PrunedSaveRow({ item }: { item: SavedItem }) {
  return (
    <Card className="p-4">
      <h3 className="font-serif text-base font-semibold leading-snug text-[var(--text-primary)]">
        {item.title}
      </h3>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
        {[
          item.subtitle,
          item.deadline_date
            ? deadlineLabel(item.deadline_kind, item.deadline_date)
            : "",
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <span className="text-xs italic text-[var(--text-muted)]">
          Original listing has closed — kept from your save.
        </span>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
          >
            Open
            <ArrowRightIcon
              size={13}
              aria-hidden="true"
              className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
            />
          </a>
        ) : null}
      </div>
    </Card>
  );
}

/** One save: the meta strip + the item's own feed-page card (or the fallback). */
function SavedRow({ item }: { item: SavedItem }) {
  const [composing, setComposing] = React.useState(false);
  const deadlines = reminderDeadlines(item);
  const canRemind = deadlines.length > 0 && item.content_id !== null;

  return (
    <div>
      <SaveMeta
        item={item}
        onRemind={canRemind ? () => setComposing(true) : undefined}
      />
      {item.card === null ? (
        <PrunedSaveRow item={item} />
      ) : item.area === "grant" ? (
        <GrantRow grant={item.card} />
      ) : item.area === "fellowship" ? (
        <FellowshipRow item={item.card} />
      ) : item.area === "conference" ? (
        <ConferenceCard conf={item.card} />
      ) : (
        <SuggestionCard suggestion={item.card} />
      )}
      {composing && item.content_id ? (
        <ReminderComposer
          contentId={item.content_id}
          title={item.title}
          deadlines={deadlines}
          onClose={() => setComposing(false)}
        />
      ) : null}
    </div>
  );
}

function SaveSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-5 w-24 rounded-full bg-surface-alt" />
        <span className="h-6 w-20 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/2 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
    </Card>
  );
}

/**
 * The Saves page: every bookmark — research papers, grants, fellowships, and
 * conferences — each rendered exactly as it appears on its own feed page, with
 * a filter rail (search, kind, deadline window, sort). Saved snapshots persist
 * even after the source listing is pruned.
 */
export function SavesSection() {
  const { data, isLoading, isError } = useSaves();
  const items = React.useMemo(() => data?.items ?? [], [data]);
  const [filters, setFilters] = React.useState<SavesFilterState>(
    DEFAULT_SAVES_FILTERS,
  );

  const options = React.useMemo(() => deriveSavesFilterOptions(items), [items]);
  const visible = React.useMemo(
    () => filterAndSortSaves(items, filters),
    [items, filters],
  );
  const within = items.filter((i) => i.within_week).length;

  const showRail = !isLoading && !isError && items.length > 0;
  const subtitle = isLoading
    ? "Gathering your saves…"
    : items.length > 0
      ? within > 0
        ? `${items.length} saved · ${within} due within a week.`
        : `${items.length} saved item${items.length === 1 ? "" : "s"}.`
      : "Papers, grants, fellowships, and conferences you bookmark collect here.";

  return (
    <div>
      <SectionHeader title="Saves" subtitle={subtitle} />
      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <SavesFilters
            options={options}
            filters={filters}
            onChange={setFilters}
            resultCount={visible.length}
            totalCount={items.length}
          />
        ) : null}

        <div className="min-w-0 flex-1">
          {isLoading ? (
            <div className="space-y-3.5">
              <SaveSkeleton />
              <SaveSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<BookmarkIcon size={26} className="text-accent" />}
              title="Couldn't load your saves"
              description="Something went wrong fetching your saved items. Please try again in a moment."
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<BookmarkIcon size={26} className="text-accent" />}
              title="Nothing saved yet"
              description="Tap the bookmark on any research paper, grant, fellowship, or conference and it will be kept here for you to come back to — deadlines raise a warning in the notification bell once they're under a week away."
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<BookmarkIcon size={26} className="text-accent" />}
              title="No saves match these filters"
              description="Try widening your filters or clearing the search to see more of your saved items."
              action={
                <button
                  type="button"
                  onClick={() => setFilters(DEFAULT_SAVES_FILTERS)}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
                >
                  Clear all filters
                </button>
              }
            />
          ) : (
            <div className="space-y-4">
              {visible.map((item, index) => (
                <div
                  key={item.id}
                  className="portal-fade-up"
                  style={{ animationDelay: `${index * 45}ms` }}
                >
                  <SavedRow item={item} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
