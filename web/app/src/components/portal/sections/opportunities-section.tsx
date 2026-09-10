"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { RevealOnScroll } from "@/components/portal/motion/reveal-on-scroll";
import { MatchCard } from "@/components/portal/primitives/match-card";
import { MatchRail } from "@/components/portal/primitives/match-rail";
import { ClusterRow } from "@/components/portal/primitives/cluster-badge";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { type ExtraDeadline } from "@/components/portal/primitives/deadline-list";
import {
  SourceRow,
  ViewLink,
} from "@/components/portal/primitives/source-footer";
import { BankIcon } from "@/components/portal/icons";
import {
  CardActionBar,
  MyloReason,
  IgnoredStrip,
  formatIsoDate,
} from "@/components/portal/sections/opportunity-bits";
import {
  DEFAULT_GRANT_FILTERS,
  GrantFilters,
  deriveGrantFilterOptions,
  filterAndSortGrants,
  type GrantFilterState,
} from "@/components/portal/sections/grant-filters";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import {
  FeedSearchBar,
  clusterOptions,
  matchesQuery,
} from "@/components/portal/primitives/feed-search-bar";
import { usePortal } from "@/components/portal/portal-context";
import { useGrants, useLabRecommendations } from "@/lib/portal/hooks";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import type {
  GrantOpportunity,
  MyLab,
  RecommendedMember,
} from "@/lib/portal/types";

/** Format an ISO date as "Jul 6, 2026" (used for Posted and the deadline).
 *
 * Both of those are date-only `YYYY-MM-DD` strings, so this delegates to
 * `formatIsoDate` rather than `new Date(iso)` — see that function for why the
 * naive form renders every date a day early west of UTC. */
function formatDate(iso: string): string {
  return formatIsoDate(iso);
}

/**
 * Every known application round for the multi-deadline hover (plan D1).
 * Unlike a conference round, a grant round carries no kind/label of its own —
 * `due_dates` is a bare, ascending-sortable array of ISO dates (`rounds` in
 * `mapping.py::_grant_deadlines`) — so rounds are numbered in chronological
 * order rather than named. A single-round grant still gets one row: "Application".
 */
/** The rounds the list shows but cannot alert on.
 *
 * A grant keeps a single addressable application deadline — its *next* round —
 * because its round identity is only ever a date, and a date-keyed round could
 * not survive the funder moving it, which is exactly what the deadline-moved
 * signal is built on. So the other rounds are real dates worth seeing and are
 * rendered read-only: earlier ones struck through, later ones plain.
 */
function grantExtraRounds(
  grant: GrantOpportunity,
  today: string,
): ExtraDeadline[] {
  const dates = [...grant.due_dates].sort();
  return dates
    .filter((iso) => iso !== grant.deadline_date)
    .map((iso, index) => ({
      key: `${iso}-${index}`,
      label:
        dates.length > 1 ? `Round ${dates.indexOf(iso) + 1}` : "Application",
      dateLabel: formatDate(iso) || iso,
      estimated: grant.dates_inferred,
      passed: iso < today,
    }));
}

/** Extra context below the round list: a letter-of-intent date ahead of the
 * full application, and the first-ever posted deadline when a funder has
 * since moved it — both real signals `due_dates` alone doesn't carry. */
function grantDeadlineFootnote(grant: GrantOpportunity): React.ReactNode {
  const lines: React.ReactNode[] = [];
  if (grant.loi_date) {
    lines.push(
      <p key="loi">
        Letter of intent due {formatDate(grant.loi_date) || grant.loi_date}
      </p>,
    );
  }
  if (
    grant.original_deadline &&
    grant.original_deadline !== grant.deadline_date
  ) {
    lines.push(
      <p key="orig">
        First posted deadline:{" "}
        {formatDate(grant.original_deadline) || grant.original_deadline}
      </p>,
    );
  }
  return lines.length > 0 ? lines : null;
}

/** One matched grant, exactly as the Grants page renders it (reused by Saves). */
export function GrantRow({
  grant,
  remindLabSlug,
  recommendedFor,
  ignorable = false,
}: {
  grant: GrantOpportunity;
  /** Set from a lab's Saves area so the reminder posts to that lab's channel. */
  remindLabSlug?: string;
  /** Lab-only: who Mylo judges this most applicable to. Personal feeds omit it. */
  recommendedFor?: RecommendedMember[];
  /**
   * Show the ignore control. Feeds pass it; the Saves page does not — a save is
   * this reader asking to keep the item, so offering to hide it there would be
   * two controls arguing about the same row.
   */
  ignorable?: boolean;
}) {
  const [ignored, setIgnored] = React.useState(false);
  // Local calendar date, for splitting rounds into gone-by and still-ahead.
  // Not `toISOString()`, which is UTC and would call a round passed a few hours
  // early for anyone east of it.
  const today = React.useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }, []);
  const posted = formatDate(grant.posted);
  // "National Institutes of Health; Original Posted Jul 16, 2024" — one line
  // that says who is behind the call and how long it has been open, with
  // either half dropping out cleanly when the source publishes neither.
  const identity = [
    grant.sponsor,
    posted ? `Original Posted ${posted}` : "",
  ]
    .filter(Boolean)
    .join("; ");
  const isMylo = grant.origin === "llm";

  // Ignored: collapse in place, with the way back, until the next refetch drops it.
  if (ignored) {
    return (
      <IgnoredStrip
        contentId={grant.content_id}
        title={grant.title}
        onRestored={() => setIgnored(false)}
      />
    );
  }

  return (
    <MatchCard
      ring={
        <MatchRail
          verdict={grant.verdict}
          position={grant.position}
          positionOf={grant.position_of}
          theme={grant.cluster?.label}
          origin={grant.origin}
          isNew={grant.is_new}
          isUpdated={grant.is_updated}
        />
      }
      head={
        /* Wraps rather than squeezing: once the title column would fall below
           12rem — a narrow phone, beside the match rail — the tools drop to
           their own line instead of crushing the title to two words a row. */
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 basis-48">
            {/* Title first, then one identity line: who is funding it, and
                when they first posted it, then the funding figure. What
                qualifies the match (New, the verdict) stays on the rail; the
                themes run as a row at the foot of this column, level with the
                Deadlines control across from them. */}
            <h3 className="font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
              {grant.title}
            </h3>
            {identity ? (
              <p
                className="mt-1.5 text-xs font-medium text-[var(--text-secondary)]"
                title={identity}
              >
                {identity}
              </p>
            ) : null}
            {grant.amount ? (
              <span
                className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]"
                title={`Funding ${grant.amount}`}
              >
                <BankIcon size={13} aria-hidden="true" />
                {grant.amount}
              </span>
            ) : null}

            <ClusterRow
              cluster={grant.cluster}
              bridgeClusters={grant.bridge_clusters}
              className="mt-2"
            />
          </div>

          {/* Ignore, reminder, bookmark — and the Deadlines control beneath
              them, spanning their width. */}
          <CardActionBar
            contentId={grant.content_id}
            title={grant.title}
            deadlines={grant.addressable_deadlines}
            extraDeadlines={grantExtraRounds(grant, today)}
            deadlineFootnote={grantDeadlineFootnote(grant)}
            saved={grant.saved}
            savedLabs={grant.saved_labs}
            remindLabSlug={remindLabSlug}
            ignorable={ignorable}
            onIgnored={() => setIgnored(true)}
          />
        </div>
      }
    >
      {grant.description ? (
        <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
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

      <RecommendedFor members={recommendedFor} />

      <SourceRow
        license={grant.license}
        licenseUrl={grant.license_url}
        sourceLinks={grant.source_links}
        source={grant.source}
        action={
          grant.url ? (
            <ViewLink href={grant.url} label="View opportunity" />
          ) : null
        }
      />
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

function GrantsList({
  grants,
  recommendedFor,
}: {
  grants: GrantOpportunity[];
  recommendedFor?: Record<string, RecommendedMember[]>;
}) {
  return (
    <div className="space-y-3.5">
      {grants.map((grant, index) => (
        <RevealOnScroll
          key={grant.content_id}
          delay={revealDelay(index, GRANT_PAGE_SIZE)}
        >
          <GrantRow
            grant={grant}
            recommendedFor={recommendedFor?.[grant.content_id]}
            ignorable
          />
        </RevealOnScroll>
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
      recommendedFor={data?.recommended_for}
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
 * The shared Grants feed body — the keyword search and cluster chips at the top,
 * the filter rail, the infinite-scroll card list, and the
 * end-of-feed marker — used identically by the personal page and a lab workspace. `labName`, when
 * set, marks the lab variant and only swaps the surrounding copy; the structure,
 * filters, and card layout are the same in both.
 */
function GrantsFeed({
  grants,
  isLoading,
  isError,
  recommendedFor,
  labName,
}: {
  grants: GrantOpportunity[];
  isLoading: boolean;
  isError: boolean;
  /** Lab-only: content id → the members Mylo judges each grant is for. */
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
}) {
  const [filters, setFilters] = React.useState<GrantFilterState>(
    DEFAULT_GRANT_FILTERS,
  );
  const [query, setQuery] = React.useState("");
  const [selectedCluster, setSelectedCluster] = React.useState<string | null>(
    null,
  );

  const clusters = React.useMemo(() => clusterOptions(grants), [grants]);

  // The top-of-page search and cluster chips scope the feed first; the rail's
  // facets then narrow whatever that scope left, so its counts read against the
  // theme the reader is looking at rather than the whole run.
  const scoped = React.useMemo(() => {
    const needle = query.trim();
    if (!needle && !selectedCluster) return grants;
    return grants.filter((g) => {
      if (selectedCluster && g.cluster?.id !== selectedCluster) return false;
      return matchesQuery(
        [g.title, g.description, g.reason, g.sponsor, g.matched_topics],
        needle,
      );
    });
  }, [grants, query, selectedCluster]);

  const options = React.useMemo(
    () => deriveGrantFilterOptions(scoped),
    [scoped],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortGrants(scoped, filters, today),
    [scoped, filters, today],
  );

  const clearAll = () => {
    setFilters(DEFAULT_GRANT_FILTERS);
    setQuery("");
    setSelectedCluster(null);
  };

  // Filters always search the full feed; the result set then streams in as the
  // reader scrolls, so reaching the bottom widens the list instead of ending it.
  const resetKey = React.useMemo(
    () => ({ filters, query, selectedCluster }),
    [filters, query, selectedCluster],
  );
  const {
    visible: displayed,
    hasMore,
    remaining,
    sentinelRef,
    revealMore,
  } = useInfiniteReveal(visible, GRANT_PAGE_SIZE, resetKey);

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

      {grants.length > 0 && !isLoading && !isError ? (
        <FeedSearchBar
          query={query}
          onQueryChange={setQuery}
          placeholder="Search grants by title, sponsor, or description…"
          clusters={clusters}
          selectedCluster={selectedCluster}
          onClusterChange={setSelectedCluster}
        />
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <GrantFilters
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
              description="Try a different search term, another cluster, or widen your filters to see more of your matched funding opportunities."
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
              <GrantsList grants={displayed} recommendedFor={recommendedFor} />
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
