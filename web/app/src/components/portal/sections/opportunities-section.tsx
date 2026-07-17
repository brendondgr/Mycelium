"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ArrowRightIcon,
  BankIcon,
  CalendarIcon,
} from "@/components/portal/icons";
import {
  MatchBadge,
  MyloReason,
  NewTag,
  SaveButton,
} from "@/components/portal/sections/opportunity-bits";
import {
  DEFAULT_GRANT_FILTERS,
  GrantFilters,
  deriveGrantFilterOptions,
  filterAndSortGrants,
  hasActiveGrantFilters,
  type GrantFilterState,
} from "@/components/portal/sections/grant-filters";
import { usePortal } from "@/components/portal/portal-context";
import { LabFeedShell } from "@/components/portal/sections/lab-feed-shell";
import { useGrants, useLabRecommendations } from "@/lib/portal/hooks";
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
export function GrantRow({ grant }: { grant: GrantOpportunity }) {
  const due = formatDate(grant.deadline_date);
  const posted = formatDate(grant.posted);
  const topics = grant.matched_topics
    .split(";")
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 5);
  const isMylo = grant.origin === "llm";

  return (
    <Card className="p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex items-start justify-between gap-3">
        {/* Left: the fit signals sit top-left, then the title and hosts. */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {grant.is_new ? <NewTag /> : null}
            <MatchBadge
              percent={grant.match_percent ?? grant.embedding_match}
              origin={grant.origin}
            />
          </div>
          <h3 className="mt-2.5 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
            {grant.title}
          </h3>
          {grant.sponsor ? (
            <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
              {grant.sponsor}
            </p>
          ) : null}
        </div>

        {/* Right: save bookmark, then the application due date and funding amount. */}
        <div className="flex shrink-0 flex-col items-end gap-2 text-right">
          <SaveButton
            contentId={grant.content_id}
            saved={grant.saved}
            savedLabs={grant.saved_labs}
            variant="icon"
          />
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

      {posted ? (
        <p className="mt-2 text-xs text-[var(--text-muted)]">Posted {posted}</p>
      ) : null}

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
        <p className="mt-2.5 text-xs text-[var(--text-muted)]">
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
    </Card>
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
          style={{ animationDelay: `${index * 50}ms` }}
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
 * Fellowships and Conferences live on their own pages.
 */
/** How many of the top recommended grants to show before "Show all". */
const DEFAULT_GRANT_LIMIT = 25;

/** The lab-scoped Grants feed (grants matched to the lab's shared profile). */
function LabGrantsFeed({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabRecommendations(lab.slug);
  const grants = data?.grants ?? [];
  return (
    <LabFeedShell
      title="Grants"
      subtitle={`Funding Mylo matched to ${lab.name}.`}
      isLoading={isLoading}
      isError={isError}
      isEmpty={grants.length === 0}
      emptyIcon={<BankIcon size={28} />}
      emptyTitle="No lab grant matches yet"
      emptyDescription="Once Mylo has run for this lab, funding opportunities matched to its purpose will appear here."
    >
      <div className="space-y-3">
        {grants.map((grant) => (
          <GrantRow key={grant.content_id} grant={grant} />
        ))}
      </div>
    </LabFeedShell>
  );
}

export function OpportunitiesSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return <LabGrantsFeed lab={currentLab} />;
  }
  return <PersonalOpportunities />;
}

function PersonalOpportunities() {
  const { data, isLoading, isError } = useGrants();
  const grants = React.useMemo(() => data?.items ?? [], [data]);
  const [filters, setFilters] = React.useState<GrantFilterState>(
    DEFAULT_GRANT_FILTERS,
  );
  const [showAll, setShowAll] = React.useState(false);

  const options = React.useMemo(
    () => deriveGrantFilterOptions(grants),
    [grants],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortGrants(grants, filters, today),
    [grants, filters, today],
  );

  // Filters always search the full feed. With no active filter, cap the view to
  // the top recommended grants until the user opts into the full list.
  const filtersActive = hasActiveGrantFilters(filters);
  const capped = !filtersActive && !showAll;
  const displayed = React.useMemo(
    () => (capped ? visible.slice(0, DEFAULT_GRANT_LIMIT) : visible),
    [visible, capped],
  );
  const hiddenCount = visible.length - displayed.length;

  const showRail = !isLoading && !isError && grants.length > 0;

  const subtitle = isLoading
    ? "Matching funding to your research…"
    : grants.length > 0
      ? `${grants.length} grant${
          grants.length === 1 ? "" : "s"
        } matched your research profile and timeline.`
      : "Funding matched to your research profile and timeline.";

  return (
    <div>
      <SectionHeader title="Grants" subtitle={subtitle} />
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
              title="Couldn't load your grants"
              description="Something went wrong fetching your funding matches. Please try again in a moment."
            />
          ) : grants.length === 0 ? (
            <EmptyState
              icon={<BankIcon size={26} className="text-accent" />}
              badge="Coming soon"
              title="Your grant matches are on their way"
              description="Once Mylo's nightly funding scan runs against your research profile, your best-fit grants — each with a percent-match score, its deadline, and why it fits — will appear here, newest strong matches pinned to the top."
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
              {hiddenCount > 0 ? (
                <div className="mt-5 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setShowAll(true)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-alt px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Show all {grants.length} grants
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
