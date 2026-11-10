"use client";

import { useAppHref } from "@/components/demo/demo-context";
import * as React from "react";

import { ClusterRow } from "@/components/portal/primitives/cluster-badge";
import { MatchCard } from "@/components/portal/primitives/match-card";
import { type ExtraDeadline } from "@/components/portal/primitives/deadline-list";
import { SourceRow, ViewLink } from "@/components/portal/primitives/source-footer";
import { BankIcon, SparkleIcon } from "@/components/portal/icons";
import {
  CardActionBar,
  MyloReason,
  IgnoredStrip,
  NewTag,
  formatIsoDate,
} from "@/components/portal/sections/opportunity-bits";
import { DetailSection } from "@/components/portal/feed/parts";
import { OpportunityFeed, type OpportunityFeedConfig } from "@/components/portal/feed/opportunity-feed";
import type { Facet } from "@/components/portal/feed/toolbar";
import { usePortal } from "@/components/portal/portal-context";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import { UsabilityStrip } from "@/components/portal/primitives/usability-strip";
import { useFellowships, useLabRecommendations } from "@/lib/portal/hooks";
import type { FellowshipOpportunity, MyLab, RecommendedMember } from "@/lib/portal/types";

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
 * The read-only row a soft deadline gets in the Deadlines control.
 *
 * A rolling or "varies" call has no date to alert on, so it projects no
 * addressable deadline and the control would otherwise render nothing at all —
 * which reads as "no deadline recorded" rather than "you can apply any time".
 * The source's own wording is kept verbatim.
 */
function fellowshipSoftRounds(item: FellowshipOpportunity): ExtraDeadline[] {
  const hasDated = item.addressable_deadlines.some((d) => d.due_date);
  if (hasDated) return [];
  const label = fellowshipDeadlineLabel(item);
  if (!label) return [];
  return [{ key: "soft", label: "Application", dateLabel: label }];
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
// Award class labels — the identity line's stand-in for a grant's sponsor
// --------------------------------------------------------------------------- //

const AWARD_CLASS_LABELS: Record<string, string> = {
  fellowship: "Fellowship",
  scholarship: "Scholarship",
  internship: "Internship",
  award: "Award",
  prize: "Prize",
};

// --------------------------------------------------------------------------- //
// Individual fellowship row card
// --------------------------------------------------------------------------- //

/** One matched fellowship, exactly as the Fellowships page renders it (reused by Saves). */
export function FellowshipRow({
  item,
  remindLabSlug,
  recommendedFor,
  ignorable = false,
}: {
  item: FellowshipOpportunity;
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
  const isMylo = item.origin === "llm";
  // "Fellowship; Original Posted Jul 16, 2024" — the grant card's identity line,
  // with the award class standing in for a sponsor a fellowship listing rarely
  // names.
  const posted = formatIsoDate(item.posted);
  const identity = [
    AWARD_CLASS_LABELS[item.award_class] ?? item.award_class,
    posted ? `Original Posted ${posted}` : "",
  ]
    .filter(Boolean)
    .join("; ");

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
      head={
        /* Wraps rather than squeezing: once the title column would fall below
           12rem — a narrow phone, beside the match rail — the tools drop to
           their own line instead of crushing the title to two words a row. */
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 basis-48">
            <h3 className="font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
              {item.title}
            </h3>
            {identity ? (
              <p
                className="mt-1.5 text-xs font-medium text-[var(--text-secondary)]"
                title={identity}
              >
                {identity}
              </p>
            ) : null}

            {/* The figure, and nothing else on the line. The source's own
                qualifier used to sit beside it in a pill, but sources write that
                field as a whole paragraph ("$100,000 per team ($50,000 per team
                member). Recipients may use the award for…"), so a chip meant to
                add two words was rendering a block of prose across the card. It
                moves into the tooltip, where its length costs the layout
                nothing, and the description below already carries the terms. */}
            {item.amount ? (
              <span
                className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]"
                title={
                  item.amount_note
                    ? `Award ${item.amount} — ${item.amount_note}`
                    : `Award ${item.amount}`
                }
              >
                <BankIcon size={13} aria-hidden="true" />
                {item.amount}
              </span>
            ) : null}

            {/* Two different claims, one row apiece: which of the reader's
                themes pulled the award in, then whether they can actually
                apply for it. */}
            <ClusterRow
              cluster={item.cluster}
              bridgeClusters={item.bridge_clusters}
              leading={item.is_new ? <NewTag /> : null}
              className="mt-2"
            />

            <div className="mt-2 flex flex-wrap items-center gap-2">
              <EligibilityBadge item={item} />
            </div>
          </div>

          <CardActionBar
            contentId={item.content_id}
            title={item.title}
            deadlines={item.addressable_deadlines}
            extraDeadlines={fellowshipSoftRounds(item)}
            saved={item.saved}
            savedLabs={item.saved_labs}
            remindLabSlug={remindLabSlug}
            ignorable={ignorable}
            onIgnored={() => setIgnored(true)}
          />
        </div>
      }
    >
      {/* The fellowship's own blurb from the source listing (matches the
          description line on grant cards). */}
      {item.description ? (
        <p className="mt-3 line-clamp-5 text-sm leading-relaxed text-[var(--text-secondary)]">
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

      {item.usability ? (
        <UsabilityStrip
          usability={item.usability}
          people={recommendedFor?.map((m) => ({ name: m.name, why: m.reason }))}
          announced={item.announcement?.discord}
          fallbackChannel="fellowships"
        />
      ) : (
        <RecommendedFor members={recommendedFor} />
      )}

      <SourceRow
        license={item.license}
        licenseUrl={item.license_url}
        sourceLinks={item.source_links}
        source={item.source}
        action={
          item.url ? (
            <ViewLink href={item.url} label="View fellowship" />
          ) : null
        }
      />
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
  const appHref = useAppHref();
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
        href={appHref("/app/profile")}
        className="font-semibold text-[var(--accent)] underline-offset-2 hover:underline"
      >
        Set your career stage
      </a>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// The feed page
// --------------------------------------------------------------------------- //

const TIER_ORDER = ["qualified", "conditional", "unverified"] as const;

function listFacet(
  id: string,
  label: string,
  items: FellowshipOpportunity[],
  values: (item: FellowshipOpportunity) => string[],
  limit = 10,
): Facet<FellowshipOpportunity>[] {
  const counts = new Map<string, number>();
  for (const item of items) for (const v of values(item)) if (v) counts.set(v, (counts.get(v) ?? 0) + 1);
  const top = [...counts].sort((a, b) => b[1] - a[1]).slice(0, limit);
  if (top.length < 2) return [];
  return [
    {
      id,
      label,
      mode: "multi",
      options: top.map(([value]) => ({ value, label: value, test: (item) => values(item).includes(value) })),
    },
  ];
}

/**
 * The Fellowships page — the shared feed (see `OpportunityFeed`) with a
 * fellowship's own parts: the eligibility verdict on the card, amount and
 * stages as its facts, eligibility / stage / citizenship / award-type filters,
 * and the eligibility, fields and limits in the opened award. Awards not tied
 * to one theme group under "Open to you".
 */
const FELLOWSHIPS_CONFIG: OpportunityFeedConfig<FellowshipOpportunity> = {
  title: "Fellowships",
  kicker: "Opportunities",
  noun: "fellowships",
  idPrefix: "fellowships",
  placeholder: "Search fellowships by title, field, or description…",
  icon: <SparkleIcon size={26} className="text-accent" />,
  source: (f) => (
    <>
      <span className="ws-src">{AWARD_CLASS_LABELS[f.award_class] ?? "Fellowship"}</span>
      {f.amount ? (
        <span className="ws-money ws-dotsep">
          <BankIcon size={13} aria-hidden="true" /> {f.amount}
        </span>
      ) : null}
    </>
  ),
  meta: (f) => {
    const parts = [f.deadline_type === "rolling" ? "Rolling" : "", f.stages.slice(0, 3).join(" / ")].filter(Boolean);
    return parts.length ? <span>{parts.join(" · ")}</span> : null;
  },
  flag: (f) => (f.tier ? <EligibilityBadge item={f} /> : null),
  about: (f) => f.description,
  aboutTitle: "About this award",
  text: (f) => [f.title, f.description, f.reason, f.fields.join(" "), f.stages.join(" "), f.eligibility.join(" ")].join(" "),
  facets: (items) => {
    const facets: Facet<FellowshipOpportunity>[] = [];
    const tiers = TIER_ORDER.filter((t) => items.some((f) => f.tier === t));
    if (tiers.length > 1) {
      facets.push({
        id: "tier",
        label: "Eligibility",
        mode: "multi",
        options: tiers.map((t) => ({ value: t, label: TIER_BADGES[t].label, test: (f) => f.tier === t })),
      });
    }
    facets.push(...listFacet("stage", "Stage", items, (f) => f.stages));
    facets.push(...listFacet("citizenship", "Citizenship", items, (f) => f.citizenship));
    facets.push(
      ...listFacet("award", "Award type", items, (f) => [AWARD_CLASS_LABELS[f.award_class] ?? f.award_class]),
    );
    return facets;
  },
  detail: (f) => (
    <>
      {f.eligibility.length || f.limits.length ? (
        <DetailSection title="Who can apply">
          <ul className="ws-meta-list">
            {[...f.eligibility, ...f.limits].map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </DetailSection>
      ) : null}
      {f.stages.length || f.citizenship.length ? (
        <DetailSection title="Stage and citizenship">
          <dl className="ws-dates">
            {f.stages.length ? (
              <div>
                <dt>Stage</dt>
                <dd>{f.stages.join(", ")}</dd>
              </div>
            ) : null}
            {f.citizenship.length ? (
              <div>
                <dt>Citizenship</dt>
                <dd>{f.citizenship.join(", ")}</dd>
              </div>
            ) : null}
            {f.amount ? (
              <div>
                <dt>Award</dt>
                <dd>
                  {f.amount}
                  {f.amount_note ? ` · ${f.amount_note}` : ""}
                </dd>
              </div>
            ) : null}
          </dl>
        </DetailSection>
      ) : null}
      {f.fields.length ? (
        <DetailSection title="Fields">
          <p>{f.fields.join(", ")}</p>
        </DetailSection>
      ) : null}
      {f.contact_email ? (
        <p className="ws-meta-text">
          Contact: <a href={`mailto:${f.contact_email}`}>{f.contact_email}</a>
        </p>
      ) : null}
    </>
  ),
  actionBar: (f) => ({ extraDeadlines: fellowshipSoftRounds(f) }),
  primaryLink: "View award",
  otherLabel: "Open to you",
  emptyTitle: "Your fellowship matches are on their way",
  emptyDescription:
    "Once your fellowship eligibility is set in your profile (citizenship, academic stage, and research fields), Mycelium will match you against the fellowship database and surface the best fits here.",
};

const LAB_FELLOWSHIPS_CONFIG: OpportunityFeedConfig<FellowshipOpportunity> = {
  ...FELLOWSHIPS_CONFIG,
  emptyTitle: "No lab fellowship matches yet",
  emptyDescription:
    "Once Mylo has run for this lab, fellowships matched to its shared research profile will appear here — each naming the members it suits best.",
};

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
    <OpportunityFeed
      config={LAB_FELLOWSHIPS_CONFIG}
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
  // `stage_set === false` means nothing placed this reader on the career
  // ladder, so the stage gate stayed silent for their whole feed. Default to
  // true while loading, so the notice never flashes on a feed that has one.
  const stageSet = data?.stage_set ?? true;
  return (
    <OpportunityFeed
      config={FELLOWSHIPS_CONFIG}
      items={items}
      isLoading={isLoading}
      isError={isError}
      banner={stageSet ? null : <StageNotice />}
    />
  );
}
