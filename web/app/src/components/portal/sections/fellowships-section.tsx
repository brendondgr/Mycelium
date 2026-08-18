"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { RevealOnScroll } from "@/components/portal/motion/reveal-on-scroll";
import { MatchCard } from "@/components/portal/primitives/match-card";
import { MatchRing } from "@/components/portal/primitives/match-ring";
import { ClusterBadge } from "@/components/portal/primitives/cluster-badge";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ArrowRightIcon,
  BankIcon,
  CalendarIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import {
  MyloReason,
  NewTag,
  RemindButton,
  IgnoreButton,
  IgnoredStrip,
  SaveButton,
  formatIsoDate,
} from "@/components/portal/sections/opportunity-bits";
import {
  DEFAULT_FELLOWSHIP_FILTERS,
  FellowshipFilters,
  deriveFellowshipFilterOptions,
  filterAndSortFellowships,
  type FellowshipFilterState,
} from "@/components/portal/sections/fellowship-filters";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import {
  FeedSearchBar,
  clusterOptions,
  matchesQuery,
} from "@/components/portal/primitives/feed-search-bar";
import { usePortal } from "@/components/portal/portal-context";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import { useFellowships, useLabRecommendations } from "@/lib/portal/hooks";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import type {
  FellowshipOpportunity,
  MyLab,
  RecommendedMember,
} from "@/lib/portal/types";

/** How many fellowships each infinite-scroll slice reveals. */
const FELLOWSHIP_PAGE_SIZE = 25;

// --------------------------------------------------------------------------- //
// Deadline display helpers
// --------------------------------------------------------------------------- //

/**
 * Derive a human-readable deadline label from a fellowship's deadline_type
 * and deadline_date fields. Handles rolling/anticipated/no-date gracefully.
 */
function fellowshipDeadlineLabel(item: FellowshipOpportunity): string {
  const { deadline_type, deadline_date } = item;
  if (deadline_type === "rolling" || deadline_type === "continuous") {
    return "Rolling deadline";
  }
  if (deadline_date) {
    // `formatIsoDate`, not `new Date(deadline_date)`: this is a date-only
    // string, which the naive constructor reads as UTC midnight and renders a
    // day early everywhere west of UTC.
    const formatted = formatIsoDate(deadline_date) || deadline_date;
    if (deadline_type === "anticipated") return `Anticipated ${formatted}`;
    return formatted;
  }
  if (deadline_type === "varies") return "Varies";
  return ""; // unknown / no date available
}

/**
 * True when the deadline is rolling or has no hard date — used to style the
 * deadline display in a softer, non-urgent color.
 */
function isSoftDeadline(item: FellowshipOpportunity): boolean {
  return (
    item.deadline_type === "rolling" ||
    item.deadline_type === "continuous" ||
    item.deadline_type === "varies" ||
    item.deadline_type === "unknown" ||
    !item.deadline_date
  );
}

// --------------------------------------------------------------------------- //
// Eligibility tier badge (a rule-engine verdict, distinct from the match ring)
// --------------------------------------------------------------------------- //

/** The label, description, and color token for each eligibility verdict. */
const TIER_BADGES: Record<
  string,
  { label: string; description: string; token: string }
> = {
  qualified: {
    label: "Qualified",
    description: "Qualified — strong eligibility match",
    token: "--success",
  },
  conditional: {
    label: "Possible fit",
    description: "Possible fit",
    token: "--warning",
  },
  unverified: {
    label: "Eligibility not listed",
    description:
      "Eligibility not listed — this award published no eligibility details, so nothing was checked",
    token: "--text-secondary",
  },
};

/**
 * The fellowship eligibility tier badge, driven by the backend verdict (`tier`)
 * independently of who wrote the reason — so it stays correct once Mylo's report
 * replaces the rule-engine headline:
 *   - "qualified"   → "Qualified" (green)
 *   - "conditional" → "Possible fit" (amber)
 *   - "unverified"  → "Eligibility not listed" (neutral)
 *
 * The tier is communicated via label + color-dot (never color alone).
 *
 * Renders nothing without a tier. A lab or project fellowship is ranked on
 * research fit alone — an institution has no citizenship or career stage — so
 * there is no eligibility verdict to report, and the badge must stay silent
 * rather than call every such card a hedged "Possible fit". Who is personally
 * eligible is said by name in the recommendation strip instead.
 *
 * "unverified" is not a judgement about the applicant: it means the award
 * published no eligibility details for us to read, so nothing was checked. Saying
 * so is the point — such a record passes every gate trivially and would otherwise
 * read as a clean "Qualified" for everybody.
 */
function EligibilityBadge({ item }: { item: FellowshipOpportunity }) {
  const badge = item.tier ? TIER_BADGES[item.tier] : undefined;
  if (!badge) return null;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
      style={{
        borderColor: `color-mix(in srgb, var(${badge.token}) 35%, var(--border))`,
        backgroundColor: `color-mix(in srgb, var(${badge.token}) 10%, var(--surface))`,
      }}
      aria-label={badge.description}
    >
      <span
        aria-hidden="true"
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: `var(${badge.token})` }}
      />
      <span className="text-xs font-bold leading-none text-[var(--text-primary)]">
        {badge.label}
      </span>
    </span>
  );
}

// --------------------------------------------------------------------------- //
// Award class chip
// --------------------------------------------------------------------------- //

const AWARD_CLASS_LABELS: Record<string, string> = {
  fellowship: "Fellowship",
  scholarship: "Scholarship",
  internship: "Internship",
  award: "Award",
  prize: "Prize",
};

function AwardClassChip({ awardClass }: { awardClass: string }) {
  const label = AWARD_CLASS_LABELS[awardClass] ?? awardClass;
  return (
    <span className="rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2.5 py-0.5 text-xs font-medium text-[var(--text-secondary)]">
      {label}
    </span>
  );
}

// --------------------------------------------------------------------------- //
// Individual fellowship row card
// --------------------------------------------------------------------------- //

/** One matched fellowship, exactly as the Fellowships page renders it (reused by Saves). */
export function FellowshipRow({
  item,
  remindLabSlug,
  recommendedFor,
  scopeName,
  ignorable = false,
}: {
  item: FellowshipOpportunity;
  /** Set from a lab's Saves area so the reminder posts to that lab's channel. */
  remindLabSlug?: string;
  /** Lab-only: who Mylo judges this most applicable to. Personal feeds omit it. */
  recommendedFor?: RecommendedMember[];
  /**
   * The lab or project this card's ring is scored against. Unset on a personal
   * feed, where the ring means the reader. A lab fellowship card can show three
   * percentages with three different scopes — this one, the member chip, and the
   * member's own-feed number in its note — so the ring has to say which is which.
   */
  scopeName?: string;
  /**
   * Show the ignore control. Feeds pass it; the Saves page does not — a save is
   * this reader asking to keep the item, so offering to hide it there would be
   * two controls arguing about the same row.
   */
  ignorable?: boolean;
}) {
  const [ignored, setIgnored] = React.useState(false);
  const deadlineLabel = fellowshipDeadlineLabel(item);
  const softDl = isSoftDeadline(item);
  const isMylo = item.origin === "llm";

  // Compact facet chips: fields + stages, capped at 4 combined
  const facetChips = [...item.fields, ...item.stages].slice(0, 4);
  const moreFacets =
    item.fields.length + item.stages.length - facetChips.length;

  // Eligibility bullets: show all if ≤3, otherwise hide behind disclosure
  const eligibilityBullets = item.eligibility;
  const SHORT_CUTOFF = 3;
  const eligibilityLong = eligibilityBullets.length > SHORT_CUTOFF;

  // Ignored: collapse in place, with the way back, until the next refetch drops it.
  if (ignored) {
    return (
      <IgnoredStrip
        contentId={item.content_id}
        title={item.title}
        onRestored={() => setIgnored(false)}
      />
    );
  }

  return (
    <MatchCard
      /* The ring is research fit; eligibility is a separate rule-engine claim
         and keeps its own badge in the head row. */
      ring={
        <MatchRing
          percent={item.match_percent}
          origin={item.origin}
          scope={scopeName}
        />
      }
      head={
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {/* Title always first, so it lines up with the top of the ring
                  whether or not this fellowship has a cluster or a New tag. */}
              <h3 className="font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
                {item.title}
              </h3>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <EligibilityBadge item={item} />
                <AwardClassChip awardClass={item.award_class} />
                {item.is_new ? <NewTag /> : null}
                {item.cluster ? <ClusterBadge cluster={item.cluster} /> : null}
              </div>
            </div>

            {/* Right: save bookmark + deadline + amount */}
            <div className="flex shrink-0 flex-col items-end gap-2 text-right">
              <div className="flex items-center gap-1.5">
                <RemindButton
                  contentId={item.content_id}
                  title={item.title}
                  deadlines={item.addressable_deadlines}
                  lockedLabSlug={remindLabSlug}
                />
                <SaveButton
                  contentId={item.content_id}
                  saved={item.saved}
                  savedLabs={item.saved_labs}
                  variant="icon"
                />
                {ignorable ? (
                  <IgnoreButton
                    contentId={item.content_id}
                    title={item.title}
                    onIgnored={() => setIgnored(true)}
                  />
                ) : null}
              </div>
              {deadlineLabel ? (
                <span
                  className={`inline-flex items-center gap-1.5 text-xs font-semibold ${
                    softDl
                      ? "text-[var(--text-secondary)]"
                      : "text-[var(--destructive)]"
                  }`}
                  title={deadlineLabel}
                >
                  <CalendarIcon size={13} aria-hidden="true" />
                  {deadlineLabel}
                </span>
              ) : null}
              {item.amount ? (
                <span
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]"
                  title={
                    item.amount_note
                      ? `${item.amount} — ${item.amount_note}`
                      : item.amount
                  }
                >
                  <BankIcon size={13} aria-hidden="true" />
                  {item.amount}
                </span>
              ) : null}
            </div>
          </div>
        </>
      }
    >
      {/* Amount note as subtext when it's a short phrase */}
      {item.amount_note && item.amount_note.length <= 40 ? (
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {item.amount_note}
        </p>
      ) : null}

      {/* The fellowship's own blurb from the source listing (matches the
          description line on grant cards). */}
      {item.description ? (
        <p className="mt-2 line-clamp-5 text-sm leading-relaxed text-[var(--text-secondary)]">
          {item.description}
        </p>
      ) : null}

      {/* Mylo's read on why this fellowship fits the researcher — the tailored
          AI report (origin "llm"); a plain rule-engine summary is the fallback. */}
      {item.reason ? (
        isMylo ? (
          <MyloReason reason={item.reason} />
        ) : (
          <p className="mt-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
            {item.reason}
          </p>
        )
      ) : null}

      {/* Eligibility bullets — short list inline, long list behind disclosure */}
      {eligibilityBullets.length > 0 ? (
        eligibilityLong ? (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-secondary)]">
              Eligibility details ({eligibilityBullets.length})
            </summary>
            <ul className="mt-2 space-y-1 pl-4">
              {eligibilityBullets.map((line) => (
                <li
                  key={line}
                  className="list-disc text-sm leading-relaxed text-[var(--text-secondary)]"
                >
                  {line}
                </li>
              ))}
            </ul>
          </details>
        ) : (
          <ul className="mt-3 space-y-1 pl-4">
            {eligibilityBullets.map((line) => (
              <li
                key={line}
                className="list-disc text-sm leading-relaxed text-[var(--text-secondary)]"
              >
                {line}
              </li>
            ))}
          </ul>
        )
      ) : null}

      {/* Facet chips: fields + stages */}
      {facetChips.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {facetChips.map((chip) => (
            <span
              key={chip}
              className="rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              {chip}
            </span>
          ))}
          {moreFacets > 0 ? (
            <span className="px-1 text-xs font-medium text-[var(--text-secondary)]">
              +{moreFacets} more
            </span>
          ) : null}
        </div>
      ) : null}

      <RecommendedFor members={recommendedFor} />

      {/* External link */}
      {item.url ? (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          View fellowship
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

// --------------------------------------------------------------------------- //
// "We don't know your career stage" notice
// --------------------------------------------------------------------------- //

/**
 * Shown on a personal feed when nothing placed the reader on the career ladder.
 *
 * The stage gate — which is what stops a postdoctoral award reaching a
 * second-year PhD student — is deliberately silent for an applicant it cannot
 * place, because gating on an absence would empty the feed instead of filtering
 * it. That trade is defensible only if the reader is told: this feed is matched
 * on research and deadlines, not on stage, and one answer changes that.
 */
function StageNotice() {
  return (
    <div
      className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border px-3.5 py-2.5 text-[13px] leading-relaxed"
      style={{
        borderColor: "color-mix(in srgb, var(--accent) 30%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)",
      }}
    >
      <span className="text-[var(--text-secondary)]">
        These are matched on research and deadlines only — we don&rsquo;t have
        your career stage, so awards meant for a later stage aren&rsquo;t being
        filtered out.
      </span>
      <a
        href="/app/profile"
        className="font-semibold text-[var(--accent)] underline-offset-2 hover:underline"
      >
        Set your career stage
      </a>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Loading skeleton
// --------------------------------------------------------------------------- //

function FellowshipSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-5 w-24 rounded-full bg-surface-alt" />
        <span className="h-6 w-20 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/3 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-5/6 rounded bg-surface-alt" />
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Animated list wrapper
// --------------------------------------------------------------------------- //

function FellowshipList({
  items,
  recommendedFor,
  labName,
}: {
  items: FellowshipOpportunity[];
  recommendedFor?: Record<string, RecommendedMember[]>;
  /** Set on a lab feed: what each card's ring is scored against. */
  labName?: string;
}) {
  return (
    <div className="space-y-3.5">
      {items.map((item, index) => (
        <RevealOnScroll
          key={item.content_id}
          delay={revealDelay(index, FELLOWSHIP_PAGE_SIZE)}
        >
          <FellowshipRow
            item={item}
            recommendedFor={recommendedFor?.[item.content_id]}
            scopeName={labName}
            ignorable
          />
        </RevealOnScroll>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Section root
// --------------------------------------------------------------------------- //

/**
 * The Fellowships page — one page, two scopes.
 *
 * A lab's Fellowships feed is structurally identical to the personal one: the
 * same filter rail, the same infinite-scroll list, the same card. It has to be —
 * a lab has no citizenship or career stage, so its fellowships are ranked on
 * research fit exactly the way its papers, grants and conferences are, and there
 * is no reason for the page to look like a different product. `labName` swaps the
 * copy and nothing else.
 *
 * The one lab-only addition is the recommendation strip on each card: who in the
 * lab Mylo judges the fellowship most applicable to, and — for members who opted
 * into sharing it — who is personally eligible.
 */
export function FellowshipsSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return <LabFellowshipsFeed lab={currentLab} />;
  }
  return <PersonalFellowships />;
}

/** The lab-scoped Fellowships feed — the lab's matches, same UI as personal. */
function LabFellowshipsFeed({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabRecommendations(lab.slug);
  const items = React.useMemo(() => data?.fellowships ?? [], [data]);
  return (
    <FellowshipsFeed
      items={items}
      isLoading={isLoading}
      isError={isError}
      recommendedFor={data?.recommended_for}
      labName={lab.name}
    />
  );
}

function PersonalFellowships() {
  const { data, isLoading, isError } = useFellowships();
  const items = React.useMemo(() => data?.items ?? [], [data]);
  return (
    <FellowshipsFeed
      items={items}
      isLoading={isLoading}
      isError={isError}
      // `stage_set === false` means nothing placed this reader on the career
      // ladder, so the stage gate stayed silent for their whole feed. Default to
      // true while loading, so the notice never flashes on a feed that has one.
      stageSet={data?.stage_set ?? true}
    />
  );
}

/**
 * The shared Fellowships feed body — the keyword search and cluster chips at the
 * top, the filter rail (tier, deadline, field,
 * stage, citizenship, award type, saved/new, sort), the loading/empty/error
 * states, and the infinite-scroll card list — used identically by the personal
 * page and a lab workspace. `labName`, when set, marks the lab variant and only
 * swaps the surrounding copy.
 */
function FellowshipsFeed({
  items,
  isLoading,
  isError,
  recommendedFor,
  labName,
  stageSet = true,
}: {
  items: FellowshipOpportunity[];
  isLoading: boolean;
  isError: boolean;
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
  /** Personal feed only: whether the reader's career stage resolved. */
  stageSet?: boolean;
}) {
  const [filters, setFilters] = React.useState<FellowshipFilterState>(
    DEFAULT_FELLOWSHIP_FILTERS,
  );
  const [query, setQuery] = React.useState("");
  const [selectedCluster, setSelectedCluster] = React.useState<string | null>(
    null,
  );

  const clusters = React.useMemo(() => clusterOptions(items), [items]);

  // The top-of-page search and cluster chips scope the feed first; the rail's
  // facets then narrow whatever that scope left, so its counts read against the
  // theme the reader is looking at rather than the whole run.
  const scoped = React.useMemo(() => {
    const needle = query.trim();
    if (!needle && !selectedCluster) return items;
    return items.filter((item) => {
      if (selectedCluster && item.cluster?.id !== selectedCluster) return false;
      return matchesQuery(
        [
          item.title,
          item.description,
          item.reason,
          item.fields.join(" "),
          item.stages.join(" "),
        ],
        needle,
      );
    });
  }, [items, query, selectedCluster]);

  const options = React.useMemo(
    () => deriveFellowshipFilterOptions(scoped),
    [scoped],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortFellowships(scoped, filters, today),
    [scoped, filters, today],
  );

  const clearAll = () => {
    setFilters(DEFAULT_FELLOWSHIP_FILTERS);
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
    useInfiniteReveal(visible, FELLOWSHIP_PAGE_SIZE, resetKey);

  const showRail = !isLoading && !isError && items.length > 0;

  // The old copy promised "fellowships you're eligible for, matched to your
  // stage" unconditionally. Eligibility filtering is only as good as what we know
  // about the reader: with no career stage on file the stage gate never fires,
  // and claiming otherwise is the kind of false confidence that made a postdoc
  // award on a student's feed read as vetted.
  const subtitle = isLoading
    ? labName
      ? `Matching fellowships to ${labName}…`
      : "Checking your eligibility…"
    : items.length > 0
      ? labName
        ? `${items.length} fellowship${
            items.length === 1 ? "" : "s"
          } Mylo matched to ${labName}.`
        : `${items.length} fellowship${
            items.length === 1 ? "" : "s"
          } matched to your research${
            stageSet ? ", career stage, and timeline" : " and timeline"
          }.`
      : labName
        ? `Fellowships matched to ${labName}.`
        : "Fellowships matched to your research, eligibility, and timeline.";

  return (
    <div>
      <SectionHeader
        eyebrow="Opportunities"
        title="Fellowships"
        subtitle={subtitle}
      />

      {!labName && !stageSet && !isLoading && !isError && items.length > 0 ? (
        <StageNotice />
      ) : null}

      {items.length > 0 && !isLoading && !isError ? (
        <FeedSearchBar
          query={query}
          onQueryChange={setQuery}
          placeholder="Search fellowships by title, field, or description…"
          clusters={clusters}
          selectedCluster={selectedCluster}
          onClusterChange={setSelectedCluster}
        />
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <FellowshipFilters
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
              <FellowshipSkeleton />
              <FellowshipSkeleton />
              <FellowshipSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<SparkleIcon size={26} className="text-accent" />}
              title={
                labName
                  ? "Couldn't load this feed"
                  : "Couldn't load your fellowships"
              }
              description={
                labName
                  ? "Something went wrong loading the lab's fellowship matches. Please try again in a moment."
                  : "Something went wrong fetching your fellowship matches. Please try again in a moment."
              }
            />
          ) : items.length === 0 ? (
            labName ? (
              <EmptyState
                icon={<SparkleIcon size={26} className="text-accent" />}
                title="No lab fellowship matches yet"
                description="Once Mylo has run for this lab, fellowships matched to its shared research profile will appear here — each naming the members it suits best."
              />
            ) : (
              <EmptyState
                icon={<SparkleIcon size={26} className="text-accent" />}
                badge="Coming soon"
                title="Your fellowship matches are on their way"
                description="Once your Fellowship eligibility is set in your profile (citizenship, academic stage, and research fields), Mycelium will match you against the fellowship database and surface the best fits here."
              />
            )
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<SparkleIcon size={26} className="text-accent" />}
              title="No fellowships match these filters"
              description="Try a different search term, another cluster, or widen your filters to see more of your matched fellowships."
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
              <FellowshipList
                items={displayed}
                recommendedFor={recommendedFor}
                labName={labName}
              />
              <FeedSentinel
                sentinelRef={sentinelRef}
                hasMore={hasMore}
                remaining={remaining}
                onRevealMore={revealMore}
                totalShown={displayed.length}
                noun="fellowships"
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
