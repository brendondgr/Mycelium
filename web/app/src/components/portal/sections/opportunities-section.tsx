"use client";

import * as React from "react";

import { MatchCard } from "@/components/portal/primitives/match-card";
import { ClusterRow } from "@/components/portal/primitives/cluster-badge";
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
  NewTag,
  UpdatedTag,
  formatIsoDate,
} from "@/components/portal/sections/opportunity-bits";
import { DetailSection } from "@/components/portal/feed/parts";
import { OpportunityFeed, type OpportunityFeedConfig } from "@/components/portal/feed/opportunity-feed";
import { usePortal } from "@/components/portal/portal-context";
import { orgRefFor, useGrants, useOrgRecommendations, type OrgRef } from "@/lib/portal/hooks";
import { TeamFitLine } from "@/components/portal/collab/team-fit-line";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import { UsabilityStrip } from "@/components/portal/primitives/usability-strip";
import type {
  GrantOpportunity,
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
  forLab = false,
  ignorable = false,
}: {
  grant: GrantOpportunity;
  /** A lab's feed: the team-fit line names lab-mates instead of "you". */
  forLab?: boolean;
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
              leading={
                <>
                  {grant.is_new ? <NewTag /> : null}
                  {grant.is_updated ? <UpdatedTag /> : null}
                </>
              }
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

      {forLab || grant.usability ? (
        <UsabilityStrip
          usability={grant.usability}
          people={recommendedFor?.map((m) => ({ name: m.name, why: m.reason }))}
          announced={grant.announcement?.discord}
          fallbackChannel="grants"
        />
      ) : null}

      <TeamFitLine
        contentId={grant.content_id}
        fit={grant.team_fit}
        title={grant.title}
        forLab={forLab}
      />

      {forLab || grant.usability ? null : <RecommendedFor members={recommendedFor} />}

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

/** "Posted Jul 6, 2026" for a card. */
function postedLabel(iso: string): string {
  return iso ? `Posted ${formatDate(iso)}` : "";
}

/**
 * The Grants page — one scrolling page of matched funding, grouped by theme,
 * with the opened call pinned on the right (see `OpportunityFeed`). The grant's
 * own parts: sponsor and amount on the card, a sponsor filter, the description,
 * team fit, and every application round behind the Deadlines menu.
 */
const GRANTS_CONFIG: OpportunityFeedConfig<GrantOpportunity> = {
  title: "Grants",
  kicker: "Opportunities",
  noun: "grants",
  idPrefix: "grants",
  kind: "grant",
  placeholder: "Search grants by title, sponsor, or description…",
  icon: <BankIcon size={26} className="text-accent" />,
  source: (g) => (
    <>
      {g.sponsor ? <span className="ws-src">{g.sponsor}</span> : null}
      {g.amount ? (
        <span className={`ws-money${g.sponsor ? " ws-dotsep" : ""}`}>
          <BankIcon size={13} aria-hidden="true" /> {g.amount}
        </span>
      ) : null}
    </>
  ),
  meta: (g) => (g.posted ? <span>{postedLabel(g.posted)}</span> : null),
  about: (g) => g.description,
  aboutTitle: "About this call",
  text: (g) => [g.title, g.description, g.reason, g.sponsor, g.matched_topics, g.opportunity_number].join(" "),
  facets: (grants) => {
    const sponsors = new Map<string, number>();
    for (const g of grants) if (g.sponsor) sponsors.set(g.sponsor, (sponsors.get(g.sponsor) ?? 0) + 1);
    const top = [...sponsors].sort((a, b) => b[1] - a[1]).slice(0, 10);
    return top.length > 1
      ? [
          {
            id: "sponsor",
            label: "Sponsor",
            mode: "multi" as const,
            options: top.map(([sponsor]) => ({
              value: sponsor,
              label: sponsor,
              test: (g: GrantOpportunity) => g.sponsor === sponsor,
            })),
          },
        ]
      : [];
  },
  sorts: [
    {
      value: "posted",
      label: "Recently posted",
      cmp: (a, b) => (b.posted || "").localeCompare(a.posted || ""),
    },
  ],
  detail: (g, { forLab }) => (
    <>
      <DetailSection title="Team fit">
        <TeamFitLine contentId={g.content_id} fit={g.team_fit} title={g.title} forLab={forLab} />
      </DetailSection>
      {g.loi_date || (g.original_deadline && g.original_deadline !== g.deadline_date) ? (
        <DetailSection title="Key dates">
          <div className="ws-meta-text">{grantDeadlineFootnote(g)}</div>
        </DetailSection>
      ) : null}
    </>
  ),
  actionBar: (g) => {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    return { extraDeadlines: grantExtraRounds(g, today), footnote: grantDeadlineFootnote(g) };
  },
  primaryLink: "View call",
  emptyTitle: "Your grant matches are on their way",
  emptyDescription:
    "Once Mylo's nightly funding scan runs against your research profile, your best-fit grants — each with its deadline and why it fits — will appear here.",
};

const LAB_GRANTS_CONFIG: OpportunityFeedConfig<GrantOpportunity> = {
  ...GRANTS_CONFIG,
  emptyTitle: "No grant matches yet",
  emptyDescription:
    "Once Mylo has run here, funding opportunities matched to this workspace's purpose will appear.",
};

export function OpportunitiesSection() {
  const { currentLab, currentDepartment } = usePortal();
  // A lab's feed, or a department's: the same feed over the org's own matches.
  const org = orgRefFor(currentLab, currentDepartment);
  if (org) {
    return <OrgGrantsFeed org={org} />;
  }
  return <PersonalOpportunities />;
}

/** The lab-scoped Grants feed — the lab's matched funding, same UI as personal. */
function OrgGrantsFeed({ org }: { org: OrgRef }) {
  const { data, isLoading, isError } = useOrgRecommendations(org);
  const grants = React.useMemo(() => data?.grants ?? [], [data]);
  return (
    <OpportunityFeed
      config={LAB_GRANTS_CONFIG}
      items={grants}
      isLoading={isLoading}
      isError={isError}
      recommendedFor={data?.recommended_for}
      labName={org.name}
    />
  );
}

function PersonalOpportunities() {
  const { data, isLoading, isError } = useGrants();
  const grants = React.useMemo(() => data?.items ?? [], [data]);
  return <OpportunityFeed config={GRANTS_CONFIG} items={grants} isLoading={isLoading} isError={isError} />;
}
