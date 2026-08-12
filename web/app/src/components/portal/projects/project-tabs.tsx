"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import {
  FeedSearchBar,
  clusterOptions,
  matchesQuery,
} from "@/components/portal/primitives/feed-search-bar";
import {
  BankIcon,
  ConferenceIcon,
  DocumentIcon,
  SparkleIcon,
  SporeNode,
} from "@/components/portal/icons";
import { ConferenceCard } from "@/components/portal/sections/conferences-section";
import { FellowshipRow } from "@/components/portal/sections/fellowships-section";
import { GrantRow } from "@/components/portal/sections/opportunities-section";
import { SuggestionCard } from "@/components/portal/sections/suggestion-card";
import {
  DEFAULT_CONFERENCE_FILTERS,
  filterAndSortConferences,
  type ConferenceSort,
} from "@/components/portal/sections/conference-filters";
import {
  DEFAULT_FELLOWSHIP_FILTERS,
  filterAndSortFellowships,
  type FellowshipSort,
} from "@/components/portal/sections/fellowship-filters";
import {
  DEFAULT_GRANT_FILTERS,
  filterAndSortGrants,
  type GrantSort,
} from "@/components/portal/sections/grant-filters";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import type {
  BriefingCategory,
  ConferenceOpportunity,
  FellowshipOpportunity,
  GrantOpportunity,
  Project,
  ProjectRecommendations,
  RecommendedMember,
  Suggestion,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** How many rows each infinite-scroll slice reveals, per area. */
const PAGE_SIZE = 10;

/** How many papers Mylo ranks itself; the rest are cross-embedding matches. */
const RANKED_PAPERS = 10;

/** Today, as the `YYYY-MM-DD` string every deadline filter compares against. */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

type AreaKey = BriefingCategory;

const AREAS: {
  key: AreaKey;
  label: string;
  noun: string;
  icon: React.ReactNode;
}[] = [
  { key: "papers", label: "Papers", noun: "papers", icon: <DocumentIcon size={15} /> },
  { key: "grants", label: "Grants", noun: "grants", icon: <BankIcon size={15} /> },
  {
    key: "conferences",
    label: "Conferences",
    noun: "conferences",
    icon: <ConferenceIcon size={15} />,
  },
  {
    key: "fellowships",
    label: "Fellowships",
    noun: "fellowships",
    icon: <SparkleIcon size={15} />,
  },
];

// ---------------------------------------------------------------------------
// Small shared controls
// ---------------------------------------------------------------------------

/** A segmented sort control — the compact stand-in for a full filter rail. */
function SortChips<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (next: T) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
        {label}
      </span>
      {options.map((option) => {
        const on = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={on}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              on
                ? "border-[color-mix(in_srgb,var(--primary)_45%,transparent)] bg-[color-mix(in_srgb,var(--primary)_12%,transparent)] text-primary"
                : "border-border bg-surface-alt text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** An on/off narrowing chip ("New only", "Open for submissions", …). */
function ToggleChip({
  on,
  onToggle,
  children,
}: {
  on: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={on}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        on
          ? "border-[color-mix(in_srgb,var(--accent)_50%,transparent)] bg-brand-accent-soft text-[color-mix(in_srgb,var(--accent)_75%,var(--text-primary))]"
          : "border-border bg-surface-alt text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
      )}
    >
      {children}
    </button>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-4" aria-hidden>
      {[0, 1, 2].map((i) => (
        <Card key={i} className="animate-pulse p-5">
          <span className="block h-4 w-2/3 rounded bg-surface-alt" />
          <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
          <span className="mt-1.5 block h-3 w-1/2 rounded bg-surface-alt" />
        </Card>
      ))}
    </div>
  );
}

/**
 * One rendered list plus its infinite-reveal foot. Every area shares it, so all
 * four tabs page, announce, and end identically — the only thing that varies is
 * the card each row renders.
 */
function AreaList<T>({
  items,
  noun,
  resetKey,
  renderItem,
  keyOf,
  dividerAt = -1,
  divider,
}: {
  items: T[];
  noun: string;
  resetKey: string;
  renderItem: (item: T) => React.ReactNode;
  keyOf: (item: T) => string;
  /** Index at which to draw `divider` (papers' cross-topics rule). */
  dividerAt?: number;
  divider?: React.ReactNode;
}) {
  const { visible, hasMore, remaining, sentinelRef, revealMore } =
    useInfiniteReveal(items, PAGE_SIZE, resetKey);

  return (
    <>
      <div className="space-y-4">
        {visible.map((item, index) => (
          <React.Fragment key={keyOf(item)}>
            {index === dividerAt ? divider : null}
            <div
              className="portal-fade-up"
              style={{ animationDelay: revealDelay(index, PAGE_SIZE, 60) }}
            >
              {renderItem(item)}
            </div>
          </React.Fragment>
        ))}
      </div>
      <FeedSentinel
        sentinelRef={sentinelRef}
        hasMore={hasMore}
        remaining={remaining}
        onRevealMore={revealMore}
        totalShown={visible.length}
        noun={noun}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// The four panels
// ---------------------------------------------------------------------------

/**
 * The Papers panel — this project's overview and the tab a reader lands on.
 * Structurally the Research Papers page: keyword search, the cluster row, and
 * Mylo's ranked picks ahead of the cross-embedding tail, all in the same
 * `SuggestionCard`.
 */
function PapersPanel({
  papers,
  recommendedFor,
}: {
  papers: Suggestion[];
  recommendedFor: Record<string, RecommendedMember[]>;
}) {
  const [query, setQuery] = React.useState("");
  const [cluster, setCluster] = React.useState<string | null>(null);
  const clusters = React.useMemo(() => clusterOptions(papers), [papers]);

  const filtering = query.trim() !== "" || cluster !== null;
  const feed = React.useMemo(() => {
    if (!filtering) return papers;
    const needle = query.trim();
    return papers.filter(
      (p) =>
        matchesQuery([p.title, p.abstract], needle) &&
        (cluster === null || p.cluster?.id === cluster),
    );
  }, [papers, filtering, query, cluster]);

  const ranked = Math.min(RANKED_PAPERS, papers.length);
  const dividerAt = !filtering && papers.length > ranked ? ranked : -1;

  return (
    <>
      {papers.length > 0 ? (
        <FeedSearchBar
          query={query}
          onQueryChange={setQuery}
          placeholder="Search this project's papers by title or abstract…"
          clusters={clusters}
          selectedCluster={cluster}
          onClusterChange={setCluster}
        />
      ) : null}

      {feed.length === 0 ? (
        <NoMatches filtering={filtering} noun="papers" />
      ) : (
        <AreaList
          items={feed}
          noun="papers"
          resetKey={`${query}|${cluster ?? ""}`}
          keyOf={(p) => p.content_id}
          dividerAt={dividerAt}
          divider={<CrossTopicsDivider />}
          renderItem={(paper) => (
            <SuggestionCard
              suggestion={paper}
              recommendedFor={recommendedFor[paper.content_id]}
            />
          )}
        />
      )}
    </>
  );
}

/** Marks where Mylo's own ranked picks end and the cross-embedding tail begins. */
function CrossTopicsDivider() {
  return (
    <div className="flex items-center gap-3 pt-2">
      <span aria-hidden className="h-px flex-1 bg-border" />
      <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
        Cross-topics matches
      </span>
      <span aria-hidden className="h-px flex-1 bg-border" />
    </div>
  );
}

function GrantsPanel({
  grants,
  recommendedFor,
}: {
  grants: GrantOpportunity[];
  recommendedFor: Record<string, RecommendedMember[]>;
}) {
  const [query, setQuery] = React.useState("");
  const [cluster, setCluster] = React.useState<string | null>(null);
  const [sort, setSort] = React.useState<GrantSort>("relevance");
  const [dueSoon, setDueSoon] = React.useState(false);
  const [newOnly, setNewOnly] = React.useState(false);
  const clusters = React.useMemo(() => clusterOptions(grants), [grants]);
  const today = React.useMemo(() => todayIso(), []);

  const feed = React.useMemo(() => {
    const narrowed = filterAndSortGrants(
      grants,
      {
        ...DEFAULT_GRANT_FILTERS,
        sort,
        deadline: dueSoon ? "d30" : "all",
        newOnly,
      },
      today,
    );
    const needle = query.trim();
    return narrowed.filter(
      (g) =>
        matchesQuery([g.title, g.sponsor, g.description], needle) &&
        (cluster === null || g.cluster?.id === cluster),
    );
  }, [grants, sort, dueSoon, newOnly, today, query, cluster]);

  const filtering = query.trim() !== "" || cluster !== null || dueSoon || newOnly;

  return (
    <>
      {grants.length > 0 ? (
        <>
          <FeedSearchBar
            query={query}
            onQueryChange={setQuery}
            placeholder="Search this project's grants by title or sponsor…"
            clusters={clusters}
            selectedCluster={cluster}
            onClusterChange={setCluster}
            className="mb-3 space-y-3"
          />
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <SortChips
              label="Sort"
              value={sort}
              onChange={setSort}
              options={[
                { value: "relevance", label: "Best fit" },
                { value: "deadline", label: "Deadline" },
                { value: "posted", label: "Newest" },
              ]}
            />
            <div className="flex flex-wrap gap-1.5">
              <ToggleChip on={dueSoon} onToggle={() => setDueSoon((v) => !v)}>
                Due within 30 days
              </ToggleChip>
              <ToggleChip on={newOnly} onToggle={() => setNewOnly((v) => !v)}>
                New only
              </ToggleChip>
            </div>
          </div>
        </>
      ) : null}

      {feed.length === 0 ? (
        <NoMatches filtering={filtering} noun="grants" />
      ) : (
        <AreaList
          items={feed}
          noun="grants"
          resetKey={`${query}|${cluster ?? ""}|${sort}|${dueSoon}|${newOnly}`}
          keyOf={(g) => g.content_id}
          renderItem={(grant) => (
            <GrantRow
              grant={grant}
              recommendedFor={recommendedFor[grant.content_id]}
            />
          )}
        />
      )}
    </>
  );
}

function ConferencesPanel({
  conferences,
  recommendedFor,
}: {
  conferences: ConferenceOpportunity[];
  recommendedFor: Record<string, RecommendedMember[]>;
}) {
  const [query, setQuery] = React.useState("");
  const [cluster, setCluster] = React.useState<string | null>(null);
  const [sort, setSort] = React.useState<ConferenceSort>("fit");
  const [openOnly, setOpenOnly] = React.useState(false);
  const [newOnly, setNewOnly] = React.useState(false);
  const clusters = React.useMemo(() => clusterOptions(conferences), [conferences]);
  const today = React.useMemo(() => todayIso(), []);

  const feed = React.useMemo(() => {
    const narrowed = filterAndSortConferences(
      conferences,
      {
        ...DEFAULT_CONFERENCE_FILTERS,
        sort,
        status: openOnly ? "open" : "any",
        newOnly,
      },
      today,
    );
    const needle = query.trim();
    return narrowed.filter(
      (c) =>
        matchesQuery([c.title, c.location, c.country, c.description], needle) &&
        (cluster === null || c.cluster?.id === cluster),
    );
  }, [conferences, sort, openOnly, newOnly, today, query, cluster]);

  const filtering = query.trim() !== "" || cluster !== null || openOnly || newOnly;

  return (
    <>
      {conferences.length > 0 ? (
        <>
          <FeedSearchBar
            query={query}
            onQueryChange={setQuery}
            placeholder="Search this project's conferences by title or place…"
            clusters={clusters}
            selectedCluster={cluster}
            onClusterChange={setCluster}
            className="mb-3 space-y-3"
          />
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <SortChips
              label="Sort"
              value={sort}
              onChange={setSort}
              options={[
                { value: "fit", label: "Best fit" },
                { value: "deadline", label: "Deadline" },
                { value: "event", label: "Event date" },
              ]}
            />
            <div className="flex flex-wrap gap-1.5">
              <ToggleChip on={openOnly} onToggle={() => setOpenOnly((v) => !v)}>
                Still open
              </ToggleChip>
              <ToggleChip on={newOnly} onToggle={() => setNewOnly((v) => !v)}>
                New only
              </ToggleChip>
            </div>
          </div>
        </>
      ) : null}

      {feed.length === 0 ? (
        <NoMatches filtering={filtering} noun="conferences" />
      ) : (
        <AreaList
          items={feed}
          noun="conferences"
          resetKey={`${query}|${cluster ?? ""}|${sort}|${openOnly}|${newOnly}`}
          keyOf={(c) => c.content_id}
          renderItem={(conf) => (
            <ConferenceCard
              conf={conf}
              recommendedFor={recommendedFor[conf.content_id]}
            />
          )}
        />
      )}
    </>
  );
}

function FellowshipsPanel({
  fellowships,
  recommendedFor,
  scopeName,
}: {
  fellowships: FellowshipOpportunity[];
  recommendedFor: Record<string, RecommendedMember[]>;
  scopeName: string;
}) {
  const [query, setQuery] = React.useState("");
  const [cluster, setCluster] = React.useState<string | null>(null);
  const [sort, setSort] = React.useState<FellowshipSort>("fit");
  const [qualified, setQualified] = React.useState(false);
  const [newOnly, setNewOnly] = React.useState(false);
  const clusters = React.useMemo(() => clusterOptions(fellowships), [fellowships]);
  const today = React.useMemo(() => todayIso(), []);

  const feed = React.useMemo(() => {
    const narrowed = filterAndSortFellowships(
      fellowships,
      {
        ...DEFAULT_FELLOWSHIP_FILTERS,
        sort,
        strength: qualified ? "qualified" : "all",
        newOnly,
      },
      today,
    );
    const needle = query.trim();
    return narrowed.filter(
      (f) =>
        matchesQuery([f.title, f.headline, f.description], needle) &&
        (cluster === null || f.cluster?.id === cluster),
    );
  }, [fellowships, sort, qualified, newOnly, today, query, cluster]);

  const filtering = query.trim() !== "" || cluster !== null || qualified || newOnly;

  return (
    <>
      {fellowships.length > 0 ? (
        <>
          <FeedSearchBar
            query={query}
            onQueryChange={setQuery}
            placeholder="Search this project's fellowships by title or description…"
            clusters={clusters}
            selectedCluster={cluster}
            onClusterChange={setCluster}
            className="mb-3 space-y-3"
          />
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <SortChips
              label="Sort"
              value={sort}
              onChange={setSort}
              options={[
                { value: "fit", label: "Best fit" },
                { value: "deadline", label: "Deadline" },
                { value: "amount", label: "Award size" },
              ]}
            />
            <div className="flex flex-wrap gap-1.5">
              <ToggleChip on={qualified} onToggle={() => setQualified((v) => !v)}>
                Strong eligibility
              </ToggleChip>
              <ToggleChip on={newOnly} onToggle={() => setNewOnly((v) => !v)}>
                New only
              </ToggleChip>
            </div>
          </div>
        </>
      ) : null}

      {feed.length === 0 ? (
        <NoMatches filtering={filtering} noun="fellowships" />
      ) : (
        <AreaList
          items={feed}
          noun="fellowships"
          resetKey={`${query}|${cluster ?? ""}|${sort}|${qualified}|${newOnly}`}
          keyOf={(f) => f.content_id}
          renderItem={(item) => (
            <FellowshipRow
              item={item}
              recommendedFor={recommendedFor[item.content_id]}
              scopeName={scopeName}
            />
          )}
        />
      )}
    </>
  );
}

/** The two "nothing here" cases an area can land in, told apart honestly. */
function NoMatches({ filtering, noun }: { filtering: boolean; noun: string }) {
  return (
    <p className="py-10 text-center text-sm text-[var(--text-secondary)]">
      {filtering
        ? `No ${noun} match these filters — clear one to widen the results.`
        : `Mylo hasn't matched any ${noun} to this project yet. New ones arrive with each daily run.`}
    </p>
  );
}

// ---------------------------------------------------------------------------
// The tab shell
// ---------------------------------------------------------------------------

/**
 * The project's four recommendation feeds behind one switch: Papers (the
 * default and the project's overview), then Grants, Conferences, and
 * Fellowships. Every panel renders the exact card its own page renders, so a
 * project's matches read the same as the personal and lab feeds — what changes
 * is that they are scored against this project's declared focus.
 *
 * An area the project has switched off in its watch settings keeps its tab but
 * says so plainly, rather than showing an empty list that looks like a failure.
 * The tablist follows the WAI-ARIA pattern: one tab stop, arrow keys to move,
 * Home / End to jump.
 */
export function ProjectRecommendationTabs({
  project,
  data,
  isLoading,
  isError,
}: {
  project: Project;
  data: ProjectRecommendations | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  const [active, setActive] = React.useState<AreaKey>("papers");
  const tabRefs = React.useRef<Record<string, HTMLButtonElement | null>>({});

  const counts = data?.counts;
  const recommendedFor = data?.recommended_for ?? {};
  const tracked = project.watch_categories;

  const onKeyDown = (event: React.KeyboardEvent) => {
    const order = AREAS.map((a) => a.key);
    const index = order.indexOf(active);
    let next: AreaKey | null = null;
    if (event.key === "ArrowRight") next = order[(index + 1) % order.length];
    if (event.key === "ArrowLeft")
      next = order[(index - 1 + order.length) % order.length];
    if (event.key === "Home") next = order[0];
    if (event.key === "End") next = order[order.length - 1];
    if (next) {
      event.preventDefault();
      setActive(next);
      tabRefs.current[next]?.focus();
    }
  };

  const panel = (() => {
    if (isLoading) return <SkeletonRows />;
    if (isError) {
      return (
        <EmptyState
          icon={<SporeNode size={26} />}
          title="Couldn't load this project's matches"
          description="Something went wrong reading what Mylo found for this project. Try again in a moment."
        />
      );
    }
    if (!tracked.includes(active)) {
      const area = AREAS.find((a) => a.key === active);
      return (
        <p className="py-10 text-center text-sm text-[var(--text-secondary)]">
          Mylo isn&apos;t tracking {area?.noun} for this project.
          {project.can_edit
            ? " Turn them on under Edit project → Mylo settings."
            : " A project editor can turn them on."}
        </p>
      );
    }
    if (active === "papers") {
      return (
        <PapersPanel
          papers={data?.papers ?? []}
          recommendedFor={recommendedFor}
        />
      );
    }
    if (active === "grants") {
      return (
        <GrantsPanel
          grants={data?.grants ?? []}
          recommendedFor={recommendedFor}
        />
      );
    }
    if (active === "conferences") {
      return (
        <ConferencesPanel
          conferences={data?.conferences ?? []}
          recommendedFor={recommendedFor}
        />
      );
    }
    return (
      <FellowshipsPanel
        fellowships={data?.fellowships ?? []}
        recommendedFor={recommendedFor}
        scopeName={project.name}
      />
    );
  })();

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-[var(--divider)] px-5 pb-0 pt-[18px]">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SporeNode size={16} className="text-primary" />
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            What Mylo found for this project
          </h2>
        </div>

        <div
          role="tablist"
          aria-label="Recommendation areas"
          onKeyDown={onKeyDown}
          className="-mb-px flex flex-wrap gap-1"
        >
          {AREAS.map((area) => {
            const on = area.key === active;
            const count = counts?.[area.key];
            const off = !tracked.includes(area.key);
            return (
              <button
                key={area.key}
                ref={(node) => {
                  tabRefs.current[area.key] = node;
                }}
                type="button"
                role="tab"
                id={`project-tab-${area.key}`}
                aria-selected={on}
                aria-controls={`project-panel-${area.key}`}
                tabIndex={on ? 0 : -1}
                onClick={() => setActive(area.key)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-t-xl border-b-2 px-3.5 py-2.5 text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  on
                    ? "border-b-primary text-primary"
                    : "border-b-transparent text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-primary)]",
                )}
              >
                {area.icon}
                {area.label}
                {off ? (
                  <span className="text-[11px] font-medium text-[var(--text-muted)]">
                    off
                  </span>
                ) : typeof count === "number" ? (
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-[1px] text-[11px] font-semibold",
                      on
                        ? "bg-[color-mix(in_srgb,var(--primary)_15%,transparent)] text-primary"
                        : "bg-surface-alt text-[var(--text-secondary)]",
                    )}
                  >
                    {count}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      <div
        role="tabpanel"
        id={`project-panel-${active}`}
        aria-labelledby={`project-tab-${active}`}
        tabIndex={0}
        className="px-5 pb-5 pt-5 focus-visible:outline-none"
      >
        {panel}
      </div>
    </Card>
  );
}
