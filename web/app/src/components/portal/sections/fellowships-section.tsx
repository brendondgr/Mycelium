"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
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
  SaveButton,
} from "@/components/portal/sections/opportunity-bits";
import {
  DEFAULT_FELLOWSHIP_FILTERS,
  FellowshipFilters,
  deriveFellowshipFilterOptions,
  filterAndSortFellowships,
  hasActiveFellowshipFilters,
  type FellowshipFilterState,
} from "@/components/portal/sections/fellowship-filters";
import { usePortal } from "@/components/portal/portal-context";
import { Pill } from "@/components/portal/primitives/pill";
import { useFellowships, useLabRecommendations } from "@/lib/portal/hooks";
import type {
  FellowshipOpportunity,
  LabFellowship,
  MyLab,
} from "@/lib/portal/types";

/** How many of the top matched fellowships to show before "Show all". */
const DEFAULT_FELLOWSHIP_LIMIT = 25;

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
    const date = new Date(deadline_date);
    const formatted = Number.isNaN(date.getTime())
      ? deadline_date
      : date.toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric",
        });
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
// Eligibility tier badge (replaces MatchBadge for fellowships)
// --------------------------------------------------------------------------- //

/**
 * The fellowship eligibility tier badge. Two tiers driven by the backend
 * eligibility verdict (`tier`), independent of who wrote the reason — so it
 * stays correct once Mylo's LLM report replaces the rule-engine headline:
 *   - "qualified"   → "Qualified" (green)
 *   - "conditional" → "Possible fit" (amber)
 *
 * The tier is communicated via label + color-dot (never color alone).
 */
function EligibilityBadge({ item }: { item: FellowshipOpportunity }) {
  const isQualified = item.tier === "qualified";
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
      style={
        isQualified
          ? {
              borderColor: "color-mix(in srgb, var(--success) 35%, var(--border))",
              backgroundColor:
                "color-mix(in srgb, var(--success) 10%, var(--surface))",
            }
          : {
              borderColor: "color-mix(in srgb, var(--warning) 35%, var(--border))",
              backgroundColor:
                "color-mix(in srgb, var(--warning) 10%, var(--surface))",
            }
      }
      aria-label={
        isQualified ? "Qualified — strong eligibility match" : "Possible fit"
      }
    >
      <span
        aria-hidden="true"
        className="h-2 w-2 rounded-full"
        style={{
          backgroundColor: isQualified ? "var(--success)" : "var(--warning)",
        }}
      />
      <span className="text-xs font-bold leading-none text-[var(--text-primary)]">
        {isQualified ? "Qualified" : "Possible fit"}
      </span>
      {typeof item.match_percent === "number" ? (
        <span className="text-[10.5px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {item.match_percent}%
        </span>
      ) : null}
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
}: {
  item: FellowshipOpportunity;
  /** Set from a lab's Saves area so the reminder posts to that lab's channel. */
  remindLabSlug?: string;
}) {
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

  return (
    <Card className="p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex items-start justify-between gap-3">
        {/* Left: eligibility tier + title + award class */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {item.is_new ? <NewTag /> : null}
            <EligibilityBadge item={item} />
            {item.cluster ? <ClusterBadge cluster={item.cluster} /> : null}
          </div>
          <h3 className="mt-2.5 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
            {item.title}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <AwardClassChip awardClass={item.award_class} />
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
          </div>
          {deadlineLabel ? (
            <span
              className={`inline-flex items-center gap-1.5 text-xs font-semibold ${
                softDl
                  ? "text-[var(--text-muted)]"
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

      {/* Amount note as subtext when it's a short phrase */}
      {item.amount_note && item.amount_note.length <= 40 ? (
        <p className="mt-1 text-xs text-[var(--text-muted)]">{item.amount_note}</p>
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
            <summary className="cursor-pointer text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
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
            <span className="px-1 text-xs font-medium text-[var(--text-muted)]">
              +{moreFacets} more
            </span>
          ) : null}
        </div>
      ) : null}

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
    </Card>
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

function FellowshipList({ items }: { items: FellowshipOpportunity[] }) {
  return (
    <div className="space-y-3.5">
      {items.map((item, index) => (
        <div
          key={item.content_id}
          className="portal-fade-up"
          style={{ animationDelay: `${index * 50}ms` }}
        >
          <FellowshipRow item={item} />
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Section root
// --------------------------------------------------------------------------- //

/**
 * The Fellowships page: matched fellowships with a deterministic eligibility
 * rule engine. Shows a left-hand filter rail (tier, deadline, field, stage,
 * citizenship, award type, saved/new, sort) with instant in-memory filtering.
 * Top-25 cap before "Show all", matching the Grants page pattern.
 */
/** One lab fellowship: a fellowship a member is eligible for (union of members). */
function LabFellowshipRow({ item }: { item: LabFellowship }) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="min-w-0 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)] hover:text-primary"
          >
            {item.title}
          </a>
        ) : (
          <h3 className="min-w-0 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
            {item.title}
          </h3>
        )}
        {item.deadline_date ? (
          <span className="shrink-0 text-[12px] text-[var(--text-muted)]">
            Deadline {item.deadline_date}
          </span>
        ) : null}
      </div>
      {item.amount ? (
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          {item.amount}
        </p>
      ) : null}
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
          Eligible:
        </span>
        {item.eligible.map((member) => (
          <Pill key={member.username} tone="neutral">
            {member.name}{" "}
            <span className="text-[var(--text-muted)]">({member.tier})</span>
          </Pill>
        ))}
      </div>
    </Card>
  );
}

/**
 * The lab-scoped Fellowships feed — the union of eligible, consenting members.
 * The lab payload is a distinct data model (fellowships members are eligible
 * for, with per-member eligibility) rather than the caller's own eligibility, so
 * it keeps its member-eligibility card; it reuses the personal page's outer
 * structure — the header, loading/empty states, and top-25 "Show all" cap — for
 * a consistent shell, without the personal filter rail (the lab data lacks the
 * tier/stage/citizenship fields those filters need).
 */
function LabFellowshipsFeed({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabRecommendations(lab.slug);
  const fellowships = React.useMemo(() => data?.fellowships ?? [], [data]);
  const [showAll, setShowAll] = React.useState(false);

  const capped = !showAll;
  const displayed = React.useMemo(
    () => (capped ? fellowships.slice(0, DEFAULT_FELLOWSHIP_LIMIT) : fellowships),
    [fellowships, capped],
  );
  const hiddenCount = fellowships.length - displayed.length;

  const subtitle = isLoading
    ? `Checking what ${lab.name} members are eligible for…`
    : fellowships.length > 0
      ? `${fellowships.length} fellowship${
          fellowships.length === 1 ? "" : "s"
        } ${lab.name} members are eligible for.`
      : `Fellowships ${lab.name} members are eligible for.`;

  return (
    <div>
      <SectionHeader title="Fellowships" subtitle={subtitle} />
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
            title="Couldn't load this feed"
            description="Something went wrong loading the lab's fellowship matches. Please try again in a moment."
          />
        ) : fellowships.length === 0 ? (
          <EmptyState
            icon={<SparkleIcon size={26} className="text-accent" />}
            title="No lab fellowship matches yet"
            description="Fellowships appear here when a member is personally eligible and has opted into sharing their eligibility with the lab."
          />
        ) : (
          <>
            <div className="space-y-3.5">
              {displayed.map((item, index) => (
                <div
                  key={item.content_id}
                  className="portal-fade-up"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <LabFellowshipRow item={item} />
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
                  Show all {fellowships.length} fellowships
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
  );
}

export function FellowshipsSection() {
  const { currentLab } = usePortal();
  if (currentLab) {
    return <LabFellowshipsFeed lab={currentLab} />;
  }
  return <PersonalFellowships />;
}

function PersonalFellowships() {
  const { data, isLoading, isError } = useFellowships();
  const items = React.useMemo(() => data?.items ?? [], [data]);

  const [filters, setFilters] = React.useState<FellowshipFilterState>(
    DEFAULT_FELLOWSHIP_FILTERS,
  );
  const [showAll, setShowAll] = React.useState(false);

  const options = React.useMemo(
    () => deriveFellowshipFilterOptions(items),
    [items],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortFellowships(items, filters, today),
    [items, filters, today],
  );

  const filtersActive = hasActiveFellowshipFilters(filters);
  const capped = !filtersActive && !showAll;
  const displayed = React.useMemo(
    () => (capped ? visible.slice(0, DEFAULT_FELLOWSHIP_LIMIT) : visible),
    [visible, capped],
  );
  const hiddenCount = visible.length - displayed.length;

  const showRail = !isLoading && !isError && items.length > 0;

  const subtitle = isLoading
    ? "Checking your eligibility…"
    : items.length > 0
      ? `${items.length} fellowship${
          items.length === 1 ? "" : "s"
        } you're eligible for, matched to your stage and timeline.`
      : "Fellowships matched to your stage, eligibility, and timeline.";

  return (
    <div>
      <SectionHeader title="Fellowships" subtitle={subtitle} />

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <FellowshipFilters
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
              <FellowshipSkeleton />
              <FellowshipSkeleton />
              <FellowshipSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<SparkleIcon size={26} className="text-accent" />}
              title="Couldn't load your fellowships"
              description="Something went wrong fetching your fellowship matches. Please try again in a moment."
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<SparkleIcon size={26} className="text-accent" />}
              badge="Coming soon"
              title="Your fellowship matches are on their way"
              description="Once your Fellowship eligibility is set in your profile (citizenship, academic stage, and research fields), Mycelium will match you against the fellowship database and surface the best fits here."
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<SparkleIcon size={26} className="text-accent" />}
              title="No fellowships match these filters"
              description="Try widening your filters to see more of your matched fellowships."
              action={
                <button
                  type="button"
                  onClick={() => setFilters(DEFAULT_FELLOWSHIP_FILTERS)}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
                >
                  Clear all filters
                </button>
              }
            />
          ) : (
            <>
              <FellowshipList items={displayed} />
              {hiddenCount > 0 ? (
                <div className="mt-5 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setShowAll(true)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-alt px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Show all {items.length} fellowships
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
