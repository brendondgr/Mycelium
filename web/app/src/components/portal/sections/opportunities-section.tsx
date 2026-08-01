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
  BankIcon,
  CalendarIcon,
} from "@/components/portal/icons";
import {
  MyloReason,
  NewTag,
  RemindButton,
  SaveButton,
} from "@/components/portal/sections/opportunity-bits";
import {
  DEFAULT_GRANT_FILTERS,
  GrantFilters,
  deriveGrantFilterOptions,
  filterAndSortGrants,
  type GrantFilterState,
} from "@/components/portal/sections/grant-filters";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import { usePortal } from "@/components/portal/portal-context";
import { useGrants, useLabRecommendations } from "@/lib/portal/hooks";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import type { GrantOpportunity, MyLab } from "@/lib/portal/types";

/** Format an ISO date as "Jul 6, 2026" (used for Posted and the deadline). */
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

/** One matched grant, exactly as the Grants page renders it (reused by Saves). */
export function GrantRow({
  grant,
  remindLabSlug,
}: {
  grant: GrantOpportunity;
  /** Set from a lab's Saves area so the reminder posts to that lab's channel. */
  remindLabSlug?: string;
}) {
  const due = formatDate(grant.deadline_date);
  const posted = formatDate(grant.posted);
  const topics = grant.matched_topics
    .split(";")
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 5);
  const isMylo = grant.origin === "llm";

  return (
    <MatchCard
      ring={
        <MatchRing
          percent={grant.match_percent ?? grant.embedding_match}
          origin={grant.origin}
        />
      }
      head={
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {/* Title always first, so it lines up with the top of the ring
                  whether or not this grant has a cluster or a New tag. */}
              <h3 className="font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
                {grant.title}
              </h3>
              {grant.sponsor ? (
                <p
                  className="mt-1.5 line-clamp-1 text-xs font-medium text-[var(--text-secondary)]"
                  title={grant.sponsor}
                >
                  {grant.sponsor}
                </p>
              ) : null}
              {posted ? (
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Posted {posted}
                </p>
              ) : null}
              {grant.is_new || grant.cluster ? (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {grant.is_new ? <NewTag /> : null}
                  {grant.cluster ? (
                    <ClusterBadge cluster={grant.cluster} />
                  ) : null}
                </div>
              ) : null}
            </div>

            {/* Right: save bookmark, then the application due date and funding amount. */}
            <div className="flex shrink-0 flex-col items-end gap-2 text-right">
              <div className="flex items-center gap-1.5">
                <RemindButton
                  contentId={grant.content_id}
                  title={grant.title}
                  deadlines={grant.addressable_deadlines}
                  lockedLabSlug={remindLabSlug}
                />
                <SaveButton
                  contentId={grant.content_id}
                  saved={grant.saved}
                  savedLabs={grant.saved_labs}
                  variant="icon"
                />
              </div>
              {due ? (
                <span
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--destructive)]"
                  title={`Deadline ${due}`}
                >
                  <CalendarIcon size={13} aria-hidden="true" />
                  {due}
                </span>
              ) : null}
              {grant.amount ? (
                <span
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]"
                  title={`Funding ${grant.amount}`}
                >
                  <BankIcon size={13} aria-hidden="true" />
                  {grant.amount}
                </span>
              ) : null}
            </div>
          </div>
        </>
      }
    >
      {grant.description ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          {grant.description}
        </p>
      ) : null}

      {/* Mylo's read on why this fits — a soft green field flags the AI note. */}
      {grant.reason ? (
        isMylo ? (
          <MyloReason reason={grant.reason} />
        ) : (
          <p className="mt-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
            {grant.reason}
          </p>
        )
      ) : null}

      {topics.length > 0 ? (
        <p className="mt-2.5 text-xs text-[var(--text-secondary)]">
          Matched: {topics.join(" · ")}
        </p>
      ) : null}

      {grant.url ? (
        <a
          href={grant.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          View opportunity
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

function GrantSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-5 w-20 rounded-full bg-surface-alt" />
        <span className="h-6 w-24 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/2 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
    </Card>
  );
}

function GrantsList({ grants }: { grants: GrantOpportunity[] }) {
  return (
    <div className="space-y-3.5">
      {grants.map((grant, index) => (
        <div
          key={grant.content_id}
          className="portal-fade-up"
          style={{ animationDelay: revealDelay(index, GRANT_PAGE_SIZE) }}
        >
          <GrantRow grant={grant} />
        </div>
      ))}
    </div>
  );
}

/**
 * The Grants page: matched funding opportunities in a scannable, detail-forward
 * row format, with a left-hand filter rail (match strength, deadline, sponsor,
 * matched topic, source, sort) that narrows the already-fetched feed in memory.
 * The list scrolls infinitely — slices reveal themselves as the reader nears the
 * bottom. Fellowships and Conferences live on their own pages.
 */
/** How many grants each infinite-scroll slice reveals. */
const GRANT_PAGE_SIZE = 25;

export function OpportunitiesSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return <LabGrantsFeed lab={currentLab} />;
  }
  return <PersonalOpportunities />;
}

/** The lab-scoped Grants feed — the lab's matched funding, same UI as personal. */
function LabGrantsFeed({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabRecommendations(lab.slug);
  const grants = React.useMemo(() => data?.grants ?? [], [data]);
  return (
    <GrantsFeed
      grants={grants}
      isLoading={isLoading}
      isError={isError}
      labName={lab.name}
    />
  );
}

function PersonalOpportunities() {
  const { data, isLoading, isError } = useGrants();
  const grants = React.useMemo(() => data?.items ?? [], [data]);
  return <GrantsFeed grants={grants} isLoading={isLoading} isError={isError} />;
}

/**
 * The shared Grants feed body — the filter rail, infinite-scroll card list, and
 * end-of-feed marker — used identically by the personal page and a lab workspace. `labName`, when
 * set, marks the lab variant and only swaps the surrounding copy; the structure,
 * filters, and card layout are the same in both.
 */
function GrantsFeed({
  grants,
  isLoading,
  isError,
  labName,
}: {
  grants: GrantOpportunity[];
  isLoading: boolean;
  isError: boolean;
  labName?: string;
}) {
  const [filters, setFilters] = React.useState<GrantFilterState>(
    DEFAULT_GRANT_FILTERS,
  );

  const options = React.useMemo(
    () => deriveGrantFilterOptions(grants),
    [grants],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortGrants(grants, filters, today),
    [grants, filters, today],
  );

  // Filters always search the full feed; the result set then streams in as the
  // reader scrolls, so reaching the bottom widens the list instead of ending it.
  const { visible: displayed, hasMore, remaining, sentinelRef, revealMore } =
    useInfiniteReveal(visible, GRANT_PAGE_SIZE, filters);

  const showRail = !isLoading && !isError && grants.length > 0;

  const subtitle = isLoading
    ? labName
      ? `Matching funding to ${labName}…`
      : "Matching funding to your research…"
    : grants.length > 0
      ? labName
        ? `${grants.length} grant${
            grants.length === 1 ? "" : "s"
          } Mylo matched to ${labName}.`
        : `${grants.length} grant${
            grants.length === 1 ? "" : "s"
          } matched your research profile and timeline.`
      : labName
        ? `Funding matched to ${labName}.`
        : "Funding matched to your research profile and timeline.";

  return (
    <div>
      <SectionHeader
        eyebrow="Opportunities"
        title="Grants"
        subtitle={subtitle}
      />
      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <GrantFilters
            options={options}
            filters={filters}
            onChange={setFilters}
            resultCount={visible.length}
            totalCount={grants.length}
          />
        ) : null}

        <div className="min-w-0 flex-1">
          {isLoading ? (
            <div className="space-y-3.5">
              <GrantSkeleton />
              <GrantSkeleton />
              <GrantSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<BankIcon size={26} className="text-accent" />}
              title={
                labName
                  ? "Couldn't load this feed"
                  : "Couldn't load your grants"
              }
              description={
                labName
                  ? "Something went wrong loading the lab's funding matches. Please try again in a moment."
                  : "Something went wrong fetching your funding matches. Please try again in a moment."
              }
            />
          ) : grants.length === 0 ? (
            <EmptyState
              icon={<BankIcon size={26} className="text-accent" />}
              badge={labName ? undefined : "Coming soon"}
              title={
                labName
                  ? "No lab grant matches yet"
                  : "Your grant matches are on their way"
              }
              description={
                labName
                  ? "Once Mylo has run for this lab, funding opportunities matched to its purpose will appear here."
                  : "Once Mylo's nightly funding scan runs against your research profile, your best-fit grants — each with a percent-match score, its deadline, and why it fits — will appear here, newest strong matches pinned to the top."
              }
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<BankIcon size={26} className="text-accent" />}
              title="No grants match these filters"
              description="Try widening your filters to see more of your matched funding opportunities."
              action={
                <button
                  type="button"
                  onClick={() => setFilters(DEFAULT_GRANT_FILTERS)}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
                >
                  Clear all filters
                </button>
              }
            />
          ) : (
            <>
              <GrantsList grants={displayed} />
              <FeedSentinel
                sentinelRef={sentinelRef}
                hasMore={hasMore}
                remaining={remaining}
                onRevealMore={revealMore}
                totalShown={displayed.length}
                noun="grants"
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
