"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { MatchCard } from "@/components/portal/primitives/match-card";
import { MatchRing } from "@/components/portal/primitives/match-ring";
import { ClusterBadge } from "@/components/portal/primitives/cluster-badge";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ArrowRightIcon,
  CalendarIcon,
  CheckIcon,
  ConferenceIcon,
} from "@/components/portal/icons";
import {
  MyloReason,
  NewTag,
  RemindButton,
  SaveButton,
  deadlineLabel,
} from "@/components/portal/sections/opportunity-bits";
import {
  ConferenceFilters,
  DEFAULT_CONFERENCE_FILTERS,
  deriveConferenceFilterOptions,
  filterAndSortConferences,
  type ConferenceFilterState,
} from "@/components/portal/sections/conference-filters";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import {
  FeedSearchBar,
  clusterOptions,
  matchesQuery,
} from "@/components/portal/primitives/feed-search-bar";
import { usePortal } from "@/components/portal/portal-context";
import { useConferences, useLabRecommendations } from "@/lib/portal/hooks";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import type {
  ConferenceOpportunity,
  MyLab,
  RecommendedMember,
} from "@/lib/portal/types";

/** How many conferences each infinite-scroll slice reveals. */
const CONFERENCE_PAGE_SIZE = 24;

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
        backgroundColor:
          "color-mix(in srgb, var(--success) 10%, var(--surface))",
        color: "var(--text-primary)",
      }}
    >
      <CheckIcon size={11} aria-hidden="true" />
      {label}
    </span>
  );
}

/** One matched conference, exactly as the Conferences page renders it (reused by Saves). */
export function ConferenceCard({
  conf,
  remindLabSlug,
  recommendedFor,
}: {
  conf: ConferenceOpportunity;
  /** Set from a lab's Saves area so the reminder posts to that lab's channel. */
  remindLabSlug?: string;
  /** Lab-only: who Mylo judges this most applicable to. Personal feeds omit it. */
  recommendedFor?: RecommendedMember[];
}) {
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
    <MatchCard
      ring={
        <MatchRing
          percent={conf.match_percent ?? conf.embedding_match}
          origin={conf.origin}
        />
      }
      head={
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {/* Title always first, so it lines up with the top of the ring
                  whether or not this conference has a cluster or a New tag. */}
              <h3 className="font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
                {conf.title}
              </h3>

              {/* Where and when sit with the title beside the ring — they
                  identify the event, the way a grant's sponsor line does. */}
              <dl className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
                {where ? (
                  <div className="flex gap-2">
                    <dt className="w-12 shrink-0 font-bold text-[var(--text-secondary)]">
                      Where
                    </dt>
                    <dd className="min-w-0">{where}</dd>
                  </div>
                ) : null}
                {conf.event_dates ? (
                  <div className="flex gap-2">
                    <dt className="w-12 shrink-0 font-bold text-[var(--text-secondary)]">
                      When
                    </dt>
                    <dd>{conf.event_dates}</dd>
                  </div>
                ) : null}
              </dl>

              {conf.is_new || conf.cluster ? (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {conf.is_new ? <NewTag /> : null}
                  {conf.cluster ? (
                    <ClusterBadge cluster={conf.cluster} />
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              <RemindButton
                contentId={conf.content_id}
                title={conf.title}
                deadlines={conf.addressable_deadlines}
                lockedLabSlug={remindLabSlug}
              />
              <SaveButton
                contentId={conf.content_id}
                saved={conf.saved}
                savedLabs={conf.saved_labs}
              />
            </div>
          </div>
        </>
      }
    >
      {conf.deadline_date ? (
        <p className="mt-2.5 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--destructive)]">
          <CalendarIcon size={15} aria-hidden="true" />
          {deadlineLabel(conf.deadline_kind, conf.deadline_date)}
        </p>
      ) : null}

      {/* The venue's own blurb, when the listing carries one (many don't). */}
      {conf.description ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          {conf.description}
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
            <span className="px-1 text-xs font-medium text-[var(--text-secondary)]">
              +{moreSubjects} more
            </span>
          ) : null}
        </div>
      ) : null}

      <RecommendedFor members={recommendedFor} />

      {conf.url ? (
        <a
          href={conf.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          View conference
          <ArrowRightIcon
            size={14}
            aria-hidden="true"
            className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
          />
        </a>
      ) : null}
    </MatchCard>
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
 * recommendation order, one card per row like Papers / Grants / Fellowships
 * (percent match and any "New" tag lead each card). A left-hand filter rail
 * (submission status, abstract/paper open,
 * deadline & event-date windows, continent, country, subject, new/saved, sort)
 * narrows the already-fetched feed in memory — instant, no refetch. The results
 * scroll infinitely, revealing a slice at a time as the reader nears the bottom,
 * matching the Grants / Fellowships pattern.
 */
export function ConferencesSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return <LabConferencesFeed lab={currentLab} />;
  }
  return <PersonalConferences />;
}

/** The lab-scoped Conferences feed — the lab's matches, same UI as personal. */
function LabConferencesFeed({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabRecommendations(lab.slug);
  const conferences = React.useMemo(() => data?.conferences ?? [], [data]);
  return (
    <ConferencesFeed
      conferences={conferences}
      isLoading={isLoading}
      isError={isError}
      generatedAt={data?.generated_at ?? null}
      recommendedFor={data?.recommended_for}
      labName={lab.name}
    />
  );
}

function PersonalConferences() {
  const { data, isLoading, isError } = useConferences();
  const conferences = React.useMemo(() => data?.items ?? [], [data]);
  return (
    <ConferencesFeed
      conferences={conferences}
      isLoading={isLoading}
      isError={isError}
      generatedAt={data?.generated_at ?? null}
    />
  );
}

/**
 * The shared Conferences feed body — the keyword search and cluster chips at the
 * top, the filter rail, infinite-scroll card list,
 * and end-of-feed marker — used identically by the personal page and a lab workspace. `labName`, when
 * set, marks the lab variant and only swaps the surrounding copy; the structure,
 * filters, and card layout are the same in both.
 */
function ConferencesFeed({
  conferences,
  isLoading,
  isError,
  generatedAt,
  recommendedFor,
  labName,
}: {
  conferences: ConferenceOpportunity[];
  isLoading: boolean;
  isError: boolean;
  generatedAt: string | null;
  /** Lab-only: content id → the members Mylo judges each conference is for. */
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
}) {
  const [filters, setFilters] = React.useState<ConferenceFilterState>(
    DEFAULT_CONFERENCE_FILTERS,
  );
  const [query, setQuery] = React.useState("");
  const [selectedCluster, setSelectedCluster] = React.useState<string | null>(
    null,
  );

  const clusters = React.useMemo(
    () => clusterOptions(conferences),
    [conferences],
  );

  // The top-of-page search and cluster chips scope the feed first; the rail's
  // facets then narrow whatever that scope left, so its counts read against the
  // theme the reader is looking at rather than the whole run.
  const scoped = React.useMemo(() => {
    const needle = query.trim();
    if (!needle && !selectedCluster) return conferences;
    return conferences.filter((conf) => {
      if (selectedCluster && conf.cluster?.id !== selectedCluster) return false;
      return matchesQuery(
        [
          conf.title,
          conf.description,
          conf.reason,
          conf.location,
          conf.matched_subjects,
        ],
        needle,
      );
    });
  }, [conferences, query, selectedCluster]);

  const options = React.useMemo(
    () => deriveConferenceFilterOptions(scoped),
    [scoped],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortConferences(scoped, filters, today),
    [scoped, filters, today],
  );

  const clearAll = () => {
    setFilters(DEFAULT_CONFERENCE_FILTERS);
    setQuery("");
    setSelectedCluster(null);
  };

  // Filters always search the full feed; the result set then streams in as the
  // reader scrolls, so reaching the bottom widens the list instead of ending it.
  const resetKey = React.useMemo(
    () => ({ filters, query, selectedCluster }),
    [filters, query, selectedCluster],
  );
  const { visible: displayed, hasMore, remaining, sentinelRef, revealMore } =
    useInfiniteReveal(visible, CONFERENCE_PAGE_SIZE, resetKey);

  const showRail = !isLoading && !isError && conferences.length > 0;

  const subtitle: React.ReactNode = (() => {
    if (isLoading) {
      return labName
        ? `Gathering conferences that fit ${labName}…`
        : "Gathering conferences that fit your work…";
    }
    if (conferences.length > 0) {
      const when = formatWhen(generatedAt);
      const count = `${conferences.length} conference${
        conferences.length === 1 ? "" : "s"
      }`;
      const lead = labName
        ? `${count}, matched to ${labName}`
        : `${count}, ranked by fit`;
      return when ? `${lead} · gathered ${when}.` : `${lead}.`;
    }
    return labName
      ? `Conferences and calls for papers matched to ${labName}, best fit first.`
      : "Conferences and calls for papers matched to your research, best fit first.";
  })();

  return (
    <div>
      <SectionHeader
        eyebrow="Opportunities"
        title="Conferences"
        subtitle={subtitle}
      />

      {conferences.length > 0 && !isLoading && !isError ? (
        <FeedSearchBar
          query={query}
          onQueryChange={setQuery}
          placeholder="Search conferences by title, location, or subject…"
          clusters={clusters}
          selectedCluster={selectedCluster}
          onClusterChange={setSelectedCluster}
        />
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <ConferenceFilters
            options={options}
            filters={filters}
            onChange={setFilters}
            resultCount={visible.length}
            totalCount={scoped.length}
          />
        ) : null}

        <div className="min-w-0 flex-1">
          {isLoading ? (
            <div className="space-y-3.5">
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              title={
                labName
                  ? "Couldn't load this feed"
                  : "Couldn't load your conferences"
              }
              description={
                labName
                  ? "Something went wrong loading the lab's conference matches. Please try again in a moment."
                  : "Something went wrong fetching your conference matches. Please try again in a moment."
              }
            />
          ) : conferences.length === 0 ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              badge={labName ? undefined : "Coming soon"}
              title={
                labName
                  ? "No lab conference matches yet"
                  : "Your conference matches are on their way"
              }
              description={
                labName
                  ? "Once Mylo has run for this lab, conferences and calls for papers matching its purpose will appear here."
                  : "Once Mylo's nightly scan of calls for papers runs against your research profile, the venues that best fit your work — each with a percent match and its submission deadline — will appear here as cards."
              }
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              title="No conferences match these filters"
              description="Try a different search term, another cluster, or widen your filters to see more of your matched conferences."
              action={
                <button
                  type="button"
                  onClick={clearAll}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
                >
                  Clear all filters
                </button>
              }
            />
          ) : (
            <>
              <div className="space-y-3.5">
                {displayed.map((conf, index) => (
                  <div
                    key={conf.content_id}
                    className="portal-fade-up"
                    style={{
                      animationDelay: revealDelay(
                        index,
                        CONFERENCE_PAGE_SIZE,
                        45,
                      ),
                    }}
                  >
                    <ConferenceCard
                      conf={conf}
                      recommendedFor={recommendedFor?.[conf.content_id]}
                    />
                  </div>
                ))}
              </div>
              <FeedSentinel
                sentinelRef={sentinelRef}
                hasMore={hasMore}
                remaining={remaining}
                onRevealMore={revealMore}
                totalShown={displayed.length}
                noun="conferences"
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
