"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  BankIcon,
  BookmarkIcon,
  ConferenceIcon,
  DocumentIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import {
  RemindButton,
  deadlineLabel,
} from "@/components/portal/sections/opportunity-bits";
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
import { usePortal } from "@/components/portal/portal-context";
import { useLabSaves, useSaves } from "@/lib/portal/hooks";
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
 * it was saved, the countdown when a deadline is near, and the user's note. The
 * reminder affordance itself now lives on the card below (the bell beside Save).
 */
function SaveMeta({ item }: { item: SavedItem }) {
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
    </div>
  );
}

/**
 * The fallback row for a save whose source listing was pruned from the corpus:
 * the snapshot (title, subtitle, deadline) is all that remains, so it renders
 * as a compact card instead of the full feed layout.
 */
function PrunedSaveRow({
  item,
  remindLabSlug,
}: {
  item: SavedItem;
  remindLabSlug?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 font-serif text-base font-semibold leading-snug text-[var(--text-primary)]">
          {item.title}
        </h3>
        {item.content_id ? (
          <RemindButton
            contentId={item.content_id}
            title={item.title}
            deadlines={reminderDeadlines(item)}
            lockedLabSlug={remindLabSlug}
          />
        ) : null}
      </div>
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

/**
 * One save: the meta strip + the item's own feed-page card (or the fallback).
 * The card carries its own reminder bell (beside Save). In a lab's saved area a
 * manager's bell is pinned to that lab so the reminder posts to the lab channel;
 * everyone else gets a personal DM reminder from the same bell.
 */
function SavedRow({
  item,
  labSlug,
  canManage = true,
}: {
  item: SavedItem;
  labSlug?: string;
  canManage?: boolean;
}) {
  // A lab reminder posts to the lab channel and only a manager may create one,
  // so the card's bell is pinned to the lab only for managers viewing a lab's
  // saves. Personal saves — and non-managers — fall through to a personal DM
  // reminder (the composer's default scope) from the same bell.
  const remindLabSlug = labSlug && canManage ? labSlug : undefined;

  return (
    <div>
      <SaveMeta item={item} />
      {item.card === null ? (
        <PrunedSaveRow item={item} remindLabSlug={remindLabSlug} />
      ) : item.area === "grant" ? (
        <GrantRow grant={item.card} remindLabSlug={remindLabSlug} />
      ) : item.area === "fellowship" ? (
        <FellowshipRow item={item.card} remindLabSlug={remindLabSlug} />
      ) : item.area === "conference" ? (
        <ConferenceCard conf={item.card} remindLabSlug={remindLabSlug} />
      ) : (
        <SuggestionCard suggestion={item.card} />
      )}
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
 * The Saves page. Scope-aware: in the personal workspace it shows the caller's
 * own bookmarks; in a lab workspace it shows that **lab's shared saves** (any
 * member reads; managers get the reminder/remove affordances). Either way each
 * item renders exactly as on its own feed page, with a filter rail, and snapshots
 * persist even after the source listing is pruned.
 */
export function SavesSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return (
      <LabSavesView labSlug={currentLab.slug} labName={currentLab.name} />
    );
  }
  return <PersonalSavesView />;
}

/** The caller's personal bookmarks. */
function PersonalSavesView() {
  const { data, isLoading, isError } = useSaves();
  const items = React.useMemo(() => data?.items ?? [], [data]);
  return (
    <SavesBody
      title="Saves"
      items={items}
      isLoading={isLoading}
      isError={isError}
      loadingLabel="Gathering your saves…"
      emptyTitle="Nothing saved yet"
      emptyDescription="Tap the bookmark on any research paper, grant, fellowship, or conference and it will be kept here for you to come back to — deadlines raise a warning in the notification bell once they're under a week away."
    />
  );
}

/** A lab's shared bookmarks (members read; managers may remind/remove). */
function LabSavesView({
  labSlug,
  labName,
}: {
  labSlug: string;
  labName: string;
}) {
  const { data, isLoading, isError } = useLabSaves(labSlug);
  const items = React.useMemo(() => data?.items ?? [], [data]);
  const canManage = data?.can_manage ?? false;
  return (
    <SavesBody
      title={`${labName} · Saves`}
      items={items}
      isLoading={isLoading}
      isError={isError}
      labSlug={labSlug}
      canManage={canManage}
      loadingLabel="Gathering this lab's saves…"
      emptyTitle="No lab saves yet"
      emptyDescription={
        canManage
          ? "Save a grant, fellowship, or conference to this lab from any feed (use the bookmark dropdown), then set a channel reminder here."
          : "Your lab's managers haven't saved anything shared here yet."
      }
    />
  );
}

/** Shared body: the filter rail + the states + the list of saved rows. */
function SavesBody({
  title,
  items,
  isLoading,
  isError,
  loadingLabel,
  emptyTitle,
  emptyDescription,
  labSlug,
  canManage = true,
}: {
  title: string;
  items: SavedItem[];
  isLoading: boolean;
  isError: boolean;
  loadingLabel: string;
  emptyTitle: string;
  emptyDescription: string;
  labSlug?: string;
  canManage?: boolean;
}) {
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
    ? loadingLabel
    : items.length > 0
      ? within > 0
        ? `${items.length} saved · ${within} due within a week.`
        : `${items.length} saved item${items.length === 1 ? "" : "s"}.`
      : "Papers, grants, fellowships, and conferences bookmarked here collect for you.";

  return (
    <div>
      <SectionHeader title={title} subtitle={subtitle} />
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
              title="Couldn't load these saves"
              description="Something went wrong fetching the saved items. Please try again in a moment."
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<BookmarkIcon size={26} className="text-accent" />}
              title={emptyTitle}
              description={emptyDescription}
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
                  <SavedRow
                    item={item}
                    labSlug={labSlug}
                    canManage={canManage}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
