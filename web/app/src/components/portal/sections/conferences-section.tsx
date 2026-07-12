"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ArrowRightIcon,
  CalendarIcon,
  CheckIcon,
  ConferenceIcon,
} from "@/components/portal/icons";
import {
  MatchBadge,
  MyloReason,
  NewTag,
  SaveButton,
  deadlineLabel,
} from "@/components/portal/sections/opportunity-bits";
import {
  ConferenceFilters,
  DEFAULT_CONFERENCE_FILTERS,
  deriveConferenceFilterOptions,
  filterAndSortConferences,
  hasActiveConferenceFilters,
  type ConferenceFilterState,
} from "@/components/portal/sections/conference-filters";
import { useConferences } from "@/lib/portal/hooks";
import type { ConferenceOpportunity } from "@/lib/portal/types";

/** How many of the top matched conferences to show before "Show all". */
const DEFAULT_CONFERENCE_LIMIT = 24;

/**
 * A small green "still accepting" pill for an open submission window (abstract
 * or full paper). Communicated by label + check icon, never color alone.
 */
function OpenChip({ label }: { label: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
      style={{
        borderColor: "color-mix(in srgb, var(--success) 35%, var(--border))",
        backgroundColor: "color-mix(in srgb, var(--success) 10%, var(--surface))",
        color: "var(--text-primary)",
      }}
    >
      <CheckIcon size={11} aria-hidden="true" />
      {label}
    </span>
  );
}

/** One matched conference, exactly as the Conferences page renders it (reused by Saves). */
export function ConferenceCard({ conf }: { conf: ConferenceOpportunity }) {
  const where = conf.location || conf.country;
  // Use the semicolon-delimited subject categories, not the space-joined
  // `keywords` blob, so the tags render as real, separate chips.
  const subjects = conf.matched_subjects
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
  const shownSubjects = subjects.slice(0, 4);
  const moreSubjects = subjects.length - shownSubjects.length;

  return (
    <Card className="flex h-full flex-col p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {conf.is_new ? <NewTag /> : null}
          <MatchBadge
            percent={conf.match_percent ?? conf.embedding_match}
            origin={conf.origin}
          />
        </div>
        <SaveButton contentId={conf.content_id} saved={conf.saved} />
      </div>

      <h3 className="mt-2.5 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
        {conf.title}
      </h3>

      <dl className="mt-2.5 space-y-1.5 text-sm text-[var(--text-secondary)]">
        {where ? (
          <div className="flex gap-2">
            <dt className="w-12 shrink-0 font-bold text-[var(--text-muted)]">
              Where
            </dt>
            <dd className="min-w-0">{where}</dd>
          </div>
        ) : null}
        {conf.event_dates ? (
          <div className="flex gap-2">
            <dt className="w-12 shrink-0 font-bold text-[var(--text-muted)]">
              When
            </dt>
            <dd>{conf.event_dates}</dd>
          </div>
        ) : null}
      </dl>

      {conf.deadline_date ? (
        <p className="mt-2.5 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--destructive)]">
          <CalendarIcon size={15} aria-hidden="true" />
          {deadlineLabel(conf.deadline_kind, conf.deadline_date)}
        </p>
      ) : null}

      {/* What's still accepting — the open submission windows for this venue. */}
      {conf.abstract_open || conf.manuscript_open ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {conf.abstract_open ? <OpenChip label="Abstract open" /> : null}
          {conf.manuscript_open ? <OpenChip label="Full paper open" /> : null}
        </div>
      ) : null}

      {/* Mylo's read on why this venue fits — the AI note when the model wrote it. */}
      {conf.reason ? (
        conf.origin === "llm" ? (
          <MyloReason reason={conf.reason} />
        ) : (
          <p className="mt-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
            {conf.reason}
          </p>
        )
      ) : null}

      {shownSubjects.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {shownSubjects.map((subject) => (
            <span
              key={subject}
              className="rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              {subject}
            </span>
          ))}
          {moreSubjects > 0 ? (
            <span className="px-1 text-xs font-medium text-[var(--text-muted)]">
              +{moreSubjects} more
            </span>
          ) : null}
        </div>
      ) : null}

      {conf.url ? (
        <a
          href={conf.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-auto inline-flex items-center gap-1.5 pt-3 text-sm font-semibold text-primary hover:underline"
        >
          View conference
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

function CardSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-6 w-24 rounded-full bg-surface-alt" />
        <span className="h-6 w-20 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/2 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
    </Card>
  );
}

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * The Conferences page: calls for papers matched to the researcher, in
 * recommendation order, as a card grid (percent match and any "New" tag lead
 * each card). A left-hand filter rail (submission status, abstract/paper open,
 * deadline & event-date windows, continent, country, subject, new/saved, sort)
 * narrows the already-fetched feed in memory — instant, no refetch. Top-24 cap
 * before "Show all", matching the Grants / Fellowships pattern.
 */
export function ConferencesSection() {
  const { data, isLoading, isError } = useConferences();
  const conferences = React.useMemo(() => data?.items ?? [], [data]);

  const [filters, setFilters] = React.useState<ConferenceFilterState>(
    DEFAULT_CONFERENCE_FILTERS,
  );
  const [showAll, setShowAll] = React.useState(false);

  const options = React.useMemo(
    () => deriveConferenceFilterOptions(conferences),
    [conferences],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortConferences(conferences, filters, today),
    [conferences, filters, today],
  );

  const filtersActive = hasActiveConferenceFilters(filters);
  const capped = !filtersActive && !showAll;
  const displayed = React.useMemo(
    () => (capped ? visible.slice(0, DEFAULT_CONFERENCE_LIMIT) : visible),
    [visible, capped],
  );
  const hiddenCount = visible.length - displayed.length;

  const showRail = !isLoading && !isError && conferences.length > 0;

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering conferences that fit your work…";
    if (conferences.length > 0) {
      const when = formatWhen(data?.generated_at ?? null);
      const count = `${conferences.length} conference${
        conferences.length === 1 ? "" : "s"
      }`;
      return when
        ? `${count}, ranked by fit · gathered ${when}.`
        : `${count}, ranked by fit.`;
    }
    return "Conferences and calls for papers matched to your research, best fit first.";
  })();

  return (
    <div>
      <SectionHeader title="Conferences" subtitle={subtitle} />

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <ConferenceFilters
            options={options}
            filters={filters}
            onChange={setFilters}
            resultCount={visible.length}
            totalCount={conferences.length}
          />
        ) : null}

        <div className="min-w-0 flex-1">
          {isLoading ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              title="Couldn't load your conferences"
              description="Something went wrong fetching your conference matches. Please try again in a moment."
            />
          ) : conferences.length === 0 ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              badge="Coming soon"
              title="Your conference matches are on their way"
              description="Once Mylo's nightly scan of calls for papers runs against your research profile, the venues that best fit your work — each with a percent match and its submission deadline — will appear here as cards."
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              title="No conferences match these filters"
              description="Try widening your filters to see more of your matched conferences."
              action={
                <button
                  type="button"
                  onClick={() => setFilters(DEFAULT_CONFERENCE_FILTERS)}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
                >
                  Clear all filters
                </button>
              }
            />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {displayed.map((conf, index) => (
                  <div
                    key={conf.content_id}
                    className="portal-fade-up"
                    style={{ animationDelay: `${index * 45}ms` }}
                  >
                    <ConferenceCard conf={conf} />
                  </div>
                ))}
              </div>
              {hiddenCount > 0 ? (
                <div className="mt-5 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setShowAll(true)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-alt px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Show all {conferences.length} conferences
                    <span className="text-[var(--text-muted)]">
                      (+{hiddenCount} more)
                    </span>
                  </button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
