"use client";

import * as React from "react";
import { ExternalLink } from "lucide-react";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import { HeldBack, heldReason } from "@/components/portal/primitives/held-back";
import { SourceRow } from "@/components/portal/primitives/source-footer";
import { CheckPill, UsabilityStrip } from "@/components/portal/primitives/usability-strip";
import { DeadlinePill, FeedCard, ItemDetail, PageHead } from "@/components/portal/feed/parts";
import { ReaderLayout, groupByTheme, useReader } from "@/components/portal/feed/reader";
import { FeedToolbar, useFeedControls, type Facet, type SortOption } from "@/components/portal/feed/toolbar";
import { PageSkeleton } from "@/components/portal/skeleton";
import {
  CardActionBar,
  IgnorableCard,
  IgnoreButton,
  SaveButton,
} from "@/components/portal/sections/opportunity-bits";
import { daysUntil } from "@/components/portal/feed/parts";
import { useInfiniteReveal } from "@/lib/portal/use-infinite-reveal";
import type { OpportunityBase, RecommendedMember } from "@/lib/portal/types";

/**
 * The feed page Grants, Fellowships and Conferences share — the same
 * structure as Research Papers (one scrolling page, grouped by theme, the
 * opened item pinned on the right), so the three read as one product.
 *
 * Each feed passes what is its own: the facts on a card, its extra filters
 * and sorts, and the sections of the opened item (dates, eligibility, team
 * fit). The shared part adds theme / best-for / deadline / can-we-use-it /
 * show-only filters, the save and ignore controls, the full action bar with
 * deadline alerts in the opened item, and — on a lab feed — "Mylo held back"
 * for what fails a hard check.
 */

const PAGE_SIZE = 20;

export type OpportunityFeedConfig<T extends OpportunityBase> = {
  title: string;
  kicker: string;
  noun: string;
  /** e.g. "grant", for "No grants match…". */
  idPrefix: string;
  placeholder: string;
  icon: React.ReactNode;
  /** The card's top-left after the deadline: sponsor, acronym. */
  label: (item: T) => string;
  /** A line of key facts on the card (amount, where and when). */
  facts?: (item: T) => React.ReactNode;
  /** Prefix for the deadline pill, e.g. "Submit by ". */
  deadlinePrefix?: (item: T) => string;
  /** What the search box looks through. */
  text: (item: T) => string;
  facets?: (items: T[]) => Facet<T>[];
  sorts?: SortOption<T>[];
  /** Sections of the opened item between "best suited to" and the themes. */
  detail?: (item: T, ctx: { forLab: boolean }) => React.ReactNode;
  /** The deadline rows and footnote behind the opened item's Deadlines menu. */
  actionBar?: (item: T) => Partial<React.ComponentProps<typeof CardActionBar>>;
  primaryLink: string;
  emptyTitle: string;
  emptyDescription: string;
};

function commonFacets<T extends OpportunityBase>(
  items: T[],
  recommendedFor?: Record<string, RecommendedMember[]>,
): { lead: Facet<T>[]; tail: Facet<T>[] } {
  const lead: Facet<T>[] = [];
  const themes = new Map<string, string>();
  for (const i of items) if (i.cluster) themes.set(i.cluster.id, i.cluster.label);
  if (themes.size > 1) {
    lead.push({
      id: "theme",
      label: "Theme",
      mode: "multi",
      options: [...themes].map(([id, label]) => ({
        value: id,
        label,
        test: (i) => i.cluster?.id === id || (i.bridge_clusters ?? []).some((b) => b.id === id),
      })),
    });
  }
  if (recommendedFor) {
    const people = new Map<string, string>();
    for (const list of Object.values(recommendedFor)) for (const m of list) people.set(m.username, m.name);
    if (people.size) {
      lead.push({
        id: "who",
        label: "Best for",
        mode: "multi",
        options: [...people].map(([username, name]) => ({
          value: username,
          label: name,
          test: (i) => (recommendedFor[i.content_id] ?? []).some((m) => m.username === username),
        })),
      });
    }
  }
  const within = (n: number) => (i: T) => {
    const d = daysUntil(i.deadline_date);
    return d !== null && d >= 0 && d <= n;
  };
  lead.push({
    id: "deadline",
    label: "Deadline",
    mode: "single",
    options: [
      { value: "any", label: "Any time", test: () => true },
      { value: "14", label: "Within 2 weeks", test: within(14) },
      { value: "30", label: "Within a month", test: within(30) },
      { value: "90", label: "Within 3 months", test: within(90) },
      { value: "none", label: "No fixed date", test: (i) => !i.deadline_date },
    ],
  });

  const tail: Facet<T>[] = [];
  if (items.some((i) => i.usability)) {
    tail.push({
      id: "usable",
      label: "Can we use it?",
      mode: "multi",
      options: [
        { value: "ok", label: "Yes", test: (i) => i.usability?.verdict === "ok" },
        { value: "warn", label: "Check first", test: (i) => i.usability?.verdict === "warn" },
        { value: "unknown", label: "Unknown", test: (i) => !i.usability || i.usability.verdict === "unknown" },
      ],
    });
  }
  tail.push({
    id: "show",
    label: "Show only",
    mode: "multi",
    options: [
      { value: "new", label: "New this week", test: (i) => i.is_new },
      { value: "updated", label: "Recently changed", test: (i) => i.is_updated },
      { value: "saved", label: "Saved", test: (i) => i.saved || i.saved_labs.length > 0 },
      { value: "mylo", label: "Mylo's reasoning", test: (i) => i.origin === "llm" },
    ],
  });
  return { lead, tail };
}

function commonSorts<T extends OpportunityBase>(items: T[], extra: SortOption<T>[] = []): SortOption<T>[] {
  const order = new Map(items.map((g, i) => [g.content_id, i]));
  const pos = (g: T) => order.get(g.content_id) ?? 0;
  const due = (g: T) => g.deadline_date || "9999";
  return [
    { value: "mylo", label: "Mylo's order", cmp: (a, b) => pos(a) - pos(b) },
    { value: "deadline", label: "Deadline soonest", cmp: (a, b) => due(a).localeCompare(due(b)) || pos(a) - pos(b) },
    ...extra,
    { value: "title", label: "Title A–Z", cmp: (a, b) => a.title.localeCompare(b.title) },
  ];
}

const opportunityId = (i: OpportunityBase) => i.content_id;

export function OpportunityFeed<T extends OpportunityBase>({
  config,
  items,
  isLoading,
  isError,
  recommendedFor,
  labName,
}: {
  config: OpportunityFeedConfig<T>;
  items: T[];
  isLoading: boolean;
  isError: boolean;
  /** Lab-only: content id → the members Mylo judges each item is for. */
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
}) {
  const forLab = recommendedFor !== undefined;
  const facets = React.useMemo(() => {
    const { lead, tail } = commonFacets(items, recommendedFor);
    return [...lead, ...(config.facets?.(items) ?? []), ...tail];
  }, [items, recommendedFor, config]);
  const sorts = React.useMemo(() => commonSorts(items, config.sorts), [items, config.sorts]);
  const controls = useFeedControls({ items, facets, sorts, text: config.text });

  // On a lab feed, what fails a hard check moves to "Mylo held back".
  const held = React.useMemo(
    () => (forLab ? controls.visible.filter((i) => heldReason(i.usability)) : []),
    [controls.visible, forLab],
  );
  const listed = React.useMemo(
    () => (held.length ? controls.visible.filter((i) => !heldReason(i.usability)) : controls.visible),
    [controls.visible, held],
  );

  const resetKey = `${controls.query}|${controls.sort}|${JSON.stringify(controls.filters)}`;
  const { visible: shown, hasMore, remaining, sentinelRef, revealMore } = useInfiniteReveal(
    listed,
    PAGE_SIZE,
    resetKey,
  );
  const groups = groupByTheme(shown, (i) => i.cluster);
  const readable = React.useMemo(() => [...listed, ...held], [listed, held]);
  const reader = useReader(readable, opportunityId, groups[0]?.items[0] ?? held[0]);

  const newCount = items.filter((i) => i.is_new).length;
  const closing = items.filter((i) => {
    const d = daysUntil(i.deadline_date);
    return d !== null && d >= 0 && d <= 14;
  }).length;

  if (isLoading) {
    return (
      <div className="ws-feedpage">
        <PageSkeleton kind="feed" reader />
      </div>
    );
  }

  const lede =
    items.length === 0 ? (
      labName ? (
        `${config.title} matched to ${labName}.`
      ) : (
        `${config.title} matched to your research.`
      )
    ) : (
      <>
        {items.length} {config.noun} {labName ? `Mylo matched to ${labName}` : "matched your research"}
        {newCount ? (
          <>
            , <strong>{newCount} new</strong> this week
          </>
        ) : null}
        {closing ? (
          <>
            , <strong className="ws-gold">{closing} closing</strong> within two weeks
          </>
        ) : null}
        .
      </>
    );

  const card = (i: T, state: { selected: boolean; onOpen: () => void }) => {
    // A card flags only what needs a second look; the full list is in the opened item.
    const checks = (i.usability?.checks ?? []).filter((c) => c.key !== "team" && c.status !== "ok").slice(0, 3);
    return (
      <IgnorableCard contentId={i.content_id} title={i.title}>
        {({ onIgnored }) => (
          <FeedCard
            title={i.title}
            signal={
              <>
                <DeadlinePill date={i.deadline_date} prefix={config.deadlinePrefix?.(i)} />
                {config.label(i) ? <span className="ws-kind">{config.label(i)}</span> : null}
                {i.is_updated ? <span className="ws-pill">Changed</span> : null}
              </>
            }
            isNew={i.is_new}
            actions={
              <>
                <SaveButton contentId={i.content_id} saved={i.saved} savedLabs={i.saved_labs} variant="icon" />
                <IgnoreButton contentId={i.content_id} title={i.title} onIgnored={onIgnored} />
              </>
            }
            facts={config.facts?.(i)}
            reason={i.beats[0] || i.reason}
            byMylo={i.origin === "llm"}
            caveat={i.caveat}
            extra={
              checks.length ? (
                <ul className="flex flex-wrap gap-1.5" aria-label="Can we use this?">
                  {checks.map((c) => (
                    <CheckPill key={c.key} check={c} />
                  ))}
                </ul>
              ) : null
            }
            members={recommendedFor?.[i.content_id]}
            theme={i.cluster ?? null}
            also={i.bridge_clusters}
            selected={state.selected}
            onOpen={state.onOpen}
          />
        )}
      </IgnorableCard>
    );
  };

  const detail = (i: T) => (
    <ItemDetail
      title={i.title}
      signal={
        <>
          <DeadlinePill date={i.deadline_date} prefix={config.deadlinePrefix?.(i)} />
          {config.label(i) ? <span className="ws-kind">{config.label(i)}</span> : null}
          {i.is_new ? <span className="ws-new">New</span> : null}
        </>
      }
      facts={config.facts?.(i)}
      actions={
        <>
          {i.url ? (
            <a className="ws-btn ws-btn-solid" href={i.url} target="_blank" rel="noopener noreferrer">
              {config.primaryLink} <ExternalLink size={13} aria-hidden="true" />
            </a>
          ) : null}
          <CardActionBar
            contentId={i.content_id}
            title={i.title}
            deadlines={i.addressable_deadlines}
            saved={i.saved}
            savedLabs={i.saved_labs}
            {...config.actionBar?.(i)}
          />
        </>
      }
      byMylo={i.origin === "llm"}
      beats={i.beats}
      reason={i.reason}
      caveat={i.caveat}
      members={recommendedFor?.[i.content_id]}
      showMembers={forLab}
      theme={i.cluster ?? null}
      also={i.bridge_clusters}
      source={
        <SourceRow license={i.license} licenseUrl={i.license_url} sourceLinks={i.source_links} source={i.source} />
      }
    >
      {/* The strip carries its own "Can we use this?" heading. */}
      <UsabilityStrip usability={i.usability} announced={i.announcement?.discord} fallbackChannel={config.idPrefix} />
      {config.detail?.(i, { forLab })}
    </ItemDetail>
  );

  return (
    <div className="ws-feedpage" data-layout="reader" data-filters="bar">
      <PageHead kicker={labName ?? config.kicker} title={config.title} lede={lede} />

      {isError ? (
        <EmptyState
          icon={config.icon}
          title={labName ? "Couldn't load this feed" : `Couldn't load your ${config.noun}`}
          description="Something went wrong fetching these matches. Please try again in a moment."
        />
      ) : items.length === 0 ? (
        <EmptyState icon={config.icon} title={config.emptyTitle} description={config.emptyDescription} />
      ) : (
        <>
          <FeedToolbar
            controls={controls}
            items={items}
            facets={facets}
            sorts={sorts}
            placeholder={config.placeholder}
            noun={config.noun}
            idPrefix={config.idPrefix}
          />
          <ReaderLayout
            reader={reader}
            groups={groups}
            getId={opportunityId}
            label={config.title}
            empty={
              held.length ? null : (
                <div className="ws-empty">
                  <p>No {config.noun} match these filters.</p>
                  <button type="button" className="ws-btn ws-btn-line" onClick={controls.clear}>
                    Clear search and filters
                  </button>
                </div>
              )
            }
            renderCard={card}
            renderDetail={detail}
            after={
              <>
                <FeedSentinel
                  sentinelRef={sentinelRef}
                  hasMore={hasMore}
                  remaining={remaining}
                  onRevealMore={revealMore}
                  totalShown={shown.length}
                  noun={config.noun}
                />
                <HeldBack count={held.length} noun={config.noun}>
                  <div className="ws-feed-items">
                    {held.map((i) => (
                      <React.Fragment key={i.content_id}>
                        {card(i, { selected: reader.isSelected(i), onOpen: () => reader.open(i) })}
                      </React.Fragment>
                    ))}
                  </div>
                </HeldBack>
              </>
            }
          />
        </>
      )}
    </div>
  );
}
