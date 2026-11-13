"use client";

import * as React from "react";

import { MatchCard } from "@/components/portal/primitives/match-card";
import { ClusterRow } from "@/components/portal/primitives/cluster-badge";
import { InfoPopover } from "@/components/portal/primitives/info-popover";
import { type ExtraDeadline } from "@/components/portal/primitives/deadline-list";
import { SourceRow, ViewLink } from "@/components/portal/primitives/source-footer";
import { AlertTriangleIcon, CheckIcon, ConferenceIcon } from "@/components/portal/icons";
import {
  CardActionBar,
  MyloReason,
  IgnoredStrip,
  NewTag,
  UpdatedTag,
} from "@/components/portal/sections/opportunity-bits";
import { shortRoundLabel } from "@/components/portal/reminder-composer";
import { DetailSection } from "@/components/portal/feed/parts";
import { OpportunityFeed, type OpportunityFeedConfig } from "@/components/portal/feed/opportunity-feed";
import type { Facet } from "@/components/portal/feed/toolbar";
import { usePortal } from "@/components/portal/portal-context";
import { useConferences, useLabRecommendations, useRankingReference } from "@/lib/portal/hooks";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import { UsabilityStrip } from "@/components/portal/primitives/usability-strip";
import type {
  ConferenceOpportunity,
  ConferenceRanking,
  MyLab,
  RankingReference,
  RecommendedMember,
  StructuredDeadline,
} from "@/lib/portal/types";


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

// --------------------------------------------------------------------------- //
// Rank badges (plan D2) — the venue's quality signal
// --------------------------------------------------------------------------- //

/** Every rank badge shares this one neutral token, regardless of the letter it
 * carries. D2 keeps rankings visual-only — never affecting order, threshold,
 * or verdict — and varying the badge's color by band (gold-for-A-fading-to-
 * grey-for-C) would read as a merit ladder the badge is explicitly not. Also
 * deliberately not `--accent`: `docs/styles.md` reserves gold for opportunity
 * signals (deadlines, alerts), and a quality rank is neither. */
const RANK_BADGE_TOKEN = "--primary";

/**
 * One rank claim ("CCF A", "CORE A*") as a small pill (the `EligibilityBadge`
 * idiom: a colored dot + label in a tinted `color-mix` pill), with a
 * keyboard- and touch-reachable popover explaining what the system and the
 * specific rank mean — resolved from the backend's ranking-reference table
 * (`useRankingReference`) rather than duplicated as frontend prose.
 *
 * `badge.rank` can carry a literal asterisk ("A*", CORE's top band). It is
 * only ever interpolated into text content and an `aria-label` here — never
 * into a class name, a `data-*` selector, or a template used as CSS — so the
 * asterisk cannot break a layout or a selector; React escapes text content by
 * construction and this component never builds one.
 */
function RankBadge({
  badge,
  reference,
  referenceFailed,
}: {
  badge: ConferenceRanking;
  reference?: RankingReference;
  referenceFailed: boolean;
}) {
  const systemInfo = reference?.rank_systems[badge.system];
  const systemLabel = systemInfo?.label ?? badge.system.toUpperCase();
  const explanation = reference?.rank_explanations[badge.system]?.[badge.rank];

  return (
    <InfoPopover
      // Accessible name must literally start with the visible text ("CCF A")
      // for WCAG 2.5.3 Label in Name — a speech-input user who says "click
      // CCF A" needs that phrase to be a match, not just present somewhere in
      // the name. Putting the explanatory suffix after the exact visible
      // string, rather than interleaving "rank" into the middle of it, is
      // what keeps this true.
      triggerLabel={`${systemLabel} ${badge.rank} — what this rank means`}
      triggerClassName="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
      triggerStyle={{
        borderColor: `color-mix(in srgb, var(${RANK_BADGE_TOKEN}) 35%, var(--border))`,
        backgroundColor: `color-mix(in srgb, var(${RANK_BADGE_TOKEN}) 10%, var(--surface))`,
      }}
      trigger={
        <>
          <span
            aria-hidden="true"
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: `var(${RANK_BADGE_TOKEN})` }}
          />
          <span className="text-xs font-bold leading-none text-[var(--text-primary)]">
            {systemLabel} {badge.rank}
          </span>
        </>
      }
    >
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">
        {systemLabel} · rank {badge.rank}
      </p>
      {systemInfo?.about ? <p className="mt-1.5">{systemInfo.about}</p> : null}
      {explanation ? (
        <p className="mt-1.5">{explanation}</p>
      ) : (
        <p className="mt-1.5 italic text-[var(--text-muted)]">
          {referenceFailed
            ? "Couldn't load this rank's explanation right now."
            : "Loading…"}
        </p>
      )}
    </InfoPopover>
  );
}

/** The rank-badge row — nothing rendered when a series carries none, which is
 * true of roughly three-quarters of live series (plan D2/D5). Its absence is
 * itself a designed state: no badge simply means no ranking body has assessed
 * the venue, which is the common case and not a judgement about it. */
function RankBadgeRow({ badges }: { badges: ConferenceRanking[] }) {
  const referenceQuery = useRankingReference();
  if (badges.length === 0) return null;
  return (
    <>
      {badges.map((badge) => (
        <RankBadge
          key={`${badge.system}-${badge.rank}`}
          badge={badge}
          reference={referenceQuery.data}
          referenceFailed={referenceQuery.isError}
        />
      ))}
    </>
  );
}

// --------------------------------------------------------------------------- //
// Quality flags (plan Phase 10 / risk register) — series-level caution
// signals, display-only. The collector's own contract (`compute_red_flags`,
// `apps/scraper/collect/conferences/resolve.py`) is explicit that none of
// these are conclusive alone and none of them filter a record; the frontend
// side of that same contract is that the badge below can only ever add
// information, never remove a card from the feed.
// --------------------------------------------------------------------------- //

/** Human copy for the backend's `red_flags` slug vocabulary
 * (`compute_red_flags` in `apps/scraper/collect/conferences/resolve.py`), in
 * the "authored on the client, backend only ships the fact" idiom — these
 * slugs have no reference-table entry because they are heuristics, not a
 * taxonomy the backend maintains prose for. */
const RED_FLAG_COPY: Record<string, { label: string; explanation: string }> = {
  fees_prominent: {
    label: "Mentions a fee",
    explanation:
      "The call for papers text Mylo read prominently mentions a registration or publication fee.",
  },
  no_committee: {
    label: "No listed committee",
    explanation:
      "Mylo didn't find a program, technical, or editorial committee named in the call for papers text.",
  },
  no_publisher: {
    label: "No listed publisher",
    explanation:
      "Mylo didn't find an established publisher or proceedings series named in the call for papers text.",
  },
  multi_discipline_title: {
    label: "Broad subject title",
    explanation:
      "The venue's name spans several unrelated disciplines at once, a pattern common to broad-scope venues.",
  },
  repeated_extensions: {
    label: "Repeated deadline extensions",
    explanation:
      "This venue has pushed a submission deadline back several times in a single round.",
  },
  short_cfp_window: {
    label: "Short call window",
    explanation:
      "The call for papers first appeared implausibly close to its own deadline — not much time to prepare a submission.",
  },
};

/** A slug outside the known vocabulary above still needs to render as
 * something readable rather than a raw `snake_case` token, so the badge
 * never breaks for a flag the frontend hasn't been told about yet. */
function humanizeRedFlag(flag: string): { label: string; explanation: string } {
  const label = flag
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
  return {
    label: label || flag,
    explanation: "A quality signal Mylo recorded while reading this venue.",
  };
}

/**
 * The series-level quality-flag badge (`red_flags`) — currently empty on
 * every live row (plan Phase 10, defect 2) but wired ahead of the first
 * flagged series, on the same accessible-popover foundation as the rank
 * badges beside it. Deliberately the quietest treatment on the card (dashed
 * border, secondary text, no `--warning` fill) because the backend's own
 * docstring says none of these are conclusive alone — visually shouting
 * about a single heuristic would overstate what one flag actually means.
 * Never `--accent`: that token is reserved for opportunity signals
 * (deadlines, alerts), and a quality flag is the opposite of an opportunity.
 */
function RedFlagsBadge({ flags }: { flags: string[] }) {
  if (flags.length === 0) return null;
  const label = `Quality flag${flags.length > 1 ? "s" : ""} (${flags.length})`;
  return (
    <InfoPopover
      // Starts with the exact visible pill text — see the WCAG 2.5.3 note on
      // `RankBadge` above; every popover trigger on this card follows it.
      triggerLabel={`${label} — informational only, doesn't hide this listing`}
      triggerClassName="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-dashed border-[var(--border)] px-2.5 py-1"
      trigger={
        <>
          <AlertTriangleIcon
            size={12}
            aria-hidden="true"
            className="text-[var(--text-secondary)]"
          />
          <span className="text-xs font-semibold text-[var(--text-secondary)]">
            {label}
          </span>
        </>
      }
    >
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">
        Quality flags
      </p>
      <p className="mt-1.5">
        None of these are conclusive on their own, and none of them remove this
        listing from your feed — they&rsquo;re just what Mylo noticed while
        reading it.
      </p>
      <ul className="mt-1.5 space-y-1.5">
        {flags.map((flag) => {
          const info = RED_FLAG_COPY[flag] ?? humanizeRedFlag(flag);
          return (
            <li key={flag}>
              <span className="font-semibold text-[var(--text-primary)]">
                {info.label}
              </span>{" "}
              — {info.explanation}
            </li>
          );
        })}
      </ul>
    </InfoPopover>
  );
}

// --------------------------------------------------------------------------- //
// Multi-deadline hover (plan D1) — every round, not just the next one
// --------------------------------------------------------------------------- //

/** Human labels for the collector's full deadline-kind vocabulary
 * (`conferences/record.py::DeadlineType`) — a superset of the three kinds
 * `ContentDeadline` gates openness on (abstract/submission/everything-else),
 * because the hover shows every dated entry a venue carries, not only the
 * actionable ones. */
const CONFERENCE_DEADLINE_KIND_LABELS: Record<string, string> = {
  abstract: "Abstract",
  submission: "Full paper",
  supplementary: "Supplementary material",
  rebuttal_open: "Rebuttal opens",
  rebuttal_close: "Rebuttal closes",
  notification: "Author notification",
  camera_ready: "Camera-ready",
  registration: "Registration",
  unknown: "Deadline",
};

/** Format an ISO instant as "Jan 12, 2027" — date only; the source's own
 * timezone `basis` is not shown here, matching the scalar deadline line above
 * it on the card, which never shows a time either. */
function formatDeadlineInstant(instant: string): string {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) return instant;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** The rounds that have already gone by, for the deadline list's muted tail.
 *
 * Only the past ones: every future round now arrives as an entry of
 * `addressable_deadlines` — one per round since the per-round projection — and
 * the list renders those itself with an alert control on each. Reading the
 * future rounds out of `deadlines_structured` as well would show each of them
 * twice, once alertable and once not.
 *
 * Undated entries (`instant === null`, a TBD the source published without a
 * date) come last and count as "not upcoming": there is nothing to alert on and
 * nothing to compare against today, but dropping them would hide a deadline the
 * venue has actually announced.
 */
function passedConferenceRounds(
  deadlines: StructuredDeadline[],
  today: string,
): ExtraDeadline[] {
  return deadlines
    .filter((d) => !d.instant || d.instant.slice(0, 10) < today)
    .sort((a, b) => (a.instant ?? "").localeCompare(b.instant ?? ""))
    .map((deadline, index) => {
      const kindLabel =
        CONFERENCE_DEADLINE_KIND_LABELS[deadline.kind] ?? "Deadline";
      const round = shortRoundLabel(deadline.round_label);
      return {
        key: `${deadline.kind}-${deadline.round_label}-${index}`,
        label: round ? `${kindLabel} · ${round}` : kindLabel,
        dateLabel: deadline.instant
          ? formatDeadlineInstant(deadline.instant)
          : deadline.raw || "Date TBD",
        estimated: deadline.is_estimated,
        passed: true,
      };
    });
}

// --------------------------------------------------------------------------- //
// Quality warnings (plan Phase 10, risk register: "ICML/KDD 2026 store an
// abstract-registration date as `submission`") — per-instance caveats about
// the specific date shown above, not the series-level flags above. This is
// the ONLY signal on the card that the deadline's *kind* might be wrong: the
// backend still labels it `deadline_kind: "submission"`, so a reader who
// never opens this note has no way to know the date could really be an
// abstract-registration deadline instead of the paper deadline it looks like.
// --------------------------------------------------------------------------- //

/**
 * A calm, always-visible note directly beneath the deadline it qualifies —
 * "not buried" per the risk register, since a confidently-wrong date with a
 * silent warning attached is the exact failure being fixed. `docs/styles.md`
 * requires alerts to carry an explanation rather than a bare icon, so the
 * trigger itself states the caution in words (not just the triangle glyph),
 * and the popover holds the backend's own warning text — collector-specific
 * phrasing (invitation ids, source names) kept verbatim rather than
 * paraphrased, since paraphrasing a warning risks losing the detail that
 * made someone trust it.
 *
 * `--warning` (amber), never `--accent` (gold) — `docs/styles.md` reserves
 * gold for opportunity signals, and a caveat about a date is the opposite of
 * one. Renders nothing when the instance carries no warnings, which is true
 * of the large majority of rows.
 */
function QualityWarningNote({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="mt-2">
      <InfoPopover
        // Starts with the exact visible text ("Mylo flagged this date") —
        // the same WCAG 2.5.3 rule the badges above follow.
        triggerLabel="Mylo flagged this date — why"
        triggerClassName="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
        triggerStyle={{
          borderColor: "color-mix(in srgb, var(--warning) 45%, var(--border))",
          backgroundColor:
            "color-mix(in srgb, var(--warning) 14%, var(--surface))",
        }}
        trigger={
          <>
            <AlertTriangleIcon
              size={12}
              aria-hidden="true"
              className="text-[var(--warning)]"
            />
            <span className="text-xs font-semibold text-[var(--text-primary)]">
              Mylo flagged this date
            </span>
          </>
        }
      >
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">
          Date quality note
        </p>
        <p className="mt-1.5">
          Mylo isn&rsquo;t fully confident about the date above — it may be a
          different kind of deadline than it looks like (for example, an
          abstract-registration date rather than the paper deadline). What it
          found:
        </p>
        <ul className="mt-1.5 list-disc space-y-1 pl-4">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </InfoPopover>
    </div>
  );
}

/** One matched conference, exactly as the Conferences page renders it (reused by Saves). */
export function ConferenceCard({
  conf,
  remindLabSlug,
  recommendedFor,
  ignorable = false,
}: {
  conf: ConferenceOpportunity;
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
  // Local calendar date, for splitting rounds into "still ahead" and "gone by".
  // Not `toISOString()`, which is UTC and would call a deadline passed a few
  // hours early for anyone east of it.
  const today = React.useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }, []);
  const where = conf.location || conf.country;
  // "Vancouver, Canada; Jul 14–18, 2026" — the conference's answer to a
  // grant's "sponsor; posted" identity line: where the event is, and when.
  const identity = [where, conf.event_dates].filter(Boolean).join("; ");

  // Ignored: collapse in place, with the way back, until the next refetch drops it.
  if (ignored) {
    return (
      <IgnoredStrip
        contentId={conf.content_id}
        title={conf.title}
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
              {conf.title}
            </h3>
            {identity ? (
              <p
                className="mt-1.5 text-xs font-medium text-[var(--text-secondary)]"
                title={identity}
              >
                {identity}
              </p>
            ) : null}

            {/* Which of the reader's themes pulled this venue in. A row here
                rather than a column in the rail — see `ClusterRow`. */}
            <ClusterRow
              cluster={conf.cluster}
              bridgeClusters={conf.bridge_clusters}
              leading={
                <>
                  {conf.is_new ? <NewTag /> : null}
                  {conf.is_updated ? <UpdatedTag /> : null}
                </>
              }
              className="mt-2"
            />

            {/* Claims about the venue itself: its rank when the series carries
                one (~25% do), and any predatory-practice flags. Neither is a
                statement about the reader's fit, so neither belongs on the
                match rail — and neither belongs on the theme row above, which is
                exactly a fit claim. */}
            {conf.rank_badges.length > 0 || conf.red_flags.length > 0 ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <RankBadgeRow badges={conf.rank_badges} />
                <RedFlagsBadge flags={conf.red_flags} />
              </div>
            ) : null}
          </div>

          <CardActionBar
            contentId={conf.content_id}
            title={conf.title}
            deadlines={conf.addressable_deadlines}
            extraDeadlines={passedConferenceRounds(
              conf.deadlines_structured,
              today,
            )}
            saved={conf.saved}
            savedLabs={conf.saved_labs}
            remindLabSlug={remindLabSlug}
            ignorable={ignorable}
            onIgnored={() => setIgnored(true)}
          />
        </div>
      }
    >
      {/* Directly beneath the head that carries the date it qualifies — see
          `QualityWarningNote` above for why this can't sit anywhere quieter. */}
      <QualityWarningNote warnings={conf.quality_warnings} />

      {/* The venue's own blurb, when the listing carries one (many don't). */}
      {conf.description ? (
        <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
          {conf.description}
        </p>
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

      {/* What's still accepting — the open submission windows for this venue. */}
      {conf.abstract_open || conf.manuscript_open ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {conf.abstract_open ? <OpenChip label="Abstract open" /> : null}
          {conf.manuscript_open ? <OpenChip label="Full paper open" /> : null}
        </div>
      ) : null}

      {conf.usability ? (
        <UsabilityStrip
          usability={conf.usability}
          people={recommendedFor?.map((m) => ({ name: m.name, why: m.reason }))}
          announced={conf.announcement?.discord}
          fallbackChannel="conferences"
        />
      ) : (
        <RecommendedFor members={recommendedFor} />
      )}

      <SourceRow
        license={conf.license}
        licenseUrl={conf.license_url}
        sourceLinks={conf.source_links}
        source={conf.source}
        action={
          conf.url ? (
            <ViewLink href={conf.url} label="View conference" />
          ) : null
        }
      />
    </MatchCard>
  );
}

function localToday(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function rankValues(c: ConferenceOpportunity): string[] {
  return c.rank_badges.map((b) => `${b.system} ${b.rank}`);
}

/**
 * The Conferences page — the shared feed (see `OpportunityFeed`) with a
 * conference's own parts: the submission deadline ("Submit by …"), where and
 * when, its ranking and any red flags on the card; submission, region and
 * ranking filters; and the dates, windows, ranking and scope in the opened
 * venue. A caveat about the date itself stays directly under it.
 */
const CONFERENCES_CONFIG: OpportunityFeedConfig<ConferenceOpportunity> = {
  title: "Conferences",
  kicker: "Opportunities",
  noun: "conferences",
  idPrefix: "conferences",
  kind: "conference",
  placeholder: "Search conferences by name, place, or topic…",
  icon: <ConferenceIcon size={26} className="text-accent" />,
  source: (c) => {
    const name = [c.acronym, c.year_label].filter(Boolean).join(" ");
    const place = c.location && c.country && !c.location.includes(c.country) ? `${c.location}, ${c.country}` : c.location || c.country;
    // "Berlin, Germany, Germany" — a source that repeats a part.
    const where = place
      .split(/,\s*/)
      .filter((part, i, all) => part && part !== all[i - 1])
      .join(", ");
    return (
      <>
        {name ? <span className="ws-src">{name}</span> : null}
        {where ? <span className={name ? "ws-dotsep" : undefined}>{where}</span> : null}
      </>
    );
  },
  deadlinePrefix: () => "Submit by ",
  meta: (c) => (c.event_dates ? <span>{c.event_dates}</span> : null),
  // The card keeps only what needs a second look; rankings sit beside the
  // site link in the opened item.
  cardExtra: (c) =>
    c.quality_warnings.length || c.red_flags.length ? (
      <div className="flex flex-wrap items-center gap-1.5">
        <QualityWarningNote warnings={c.quality_warnings} />
        <RedFlagsBadge flags={c.red_flags} />
      </div>
    ) : null,
  primaryExtra: (c) =>
    c.rank_badges.length || c.red_flags.length ? (
      <>
        <RankBadgeRow badges={c.rank_badges} />
        <RedFlagsBadge flags={c.red_flags} />
      </>
    ) : null,
  about: (c) => c.description || c.scope,
  text: (c) =>
    [c.title, c.acronym, c.description, c.reason, c.location, c.country, c.keywords, c.matched_subjects, c.scope].join(" "),
  facets: (items) => {
    const facets: Facet<ConferenceOpportunity>[] = [
      {
        id: "submissions",
        label: "Submissions",
        mode: "multi",
        options: [
          { value: "abstract", label: "Abstract open", test: (c) => c.abstract_open },
          { value: "paper", label: "Full paper open", test: (c) => c.manuscript_open },
          { value: "closed", label: "Attend only", test: (c) => !c.abstract_open && !c.manuscript_open },
        ],
      },
    ];
    const countries = new Map<string, number>();
    for (const c of items) if (c.country) countries.set(c.country, (countries.get(c.country) ?? 0) + 1);
    const top = [...countries].sort((a, b) => b[1] - a[1]).slice(0, 10);
    if (top.length > 1) {
      facets.push({
        id: "region",
        label: "Where",
        mode: "multi",
        options: top.map(([country]) => ({ value: country, label: country, test: (c) => c.country === country })),
      });
    }
    const ranks = new Map<string, number>();
    for (const c of items) for (const r of rankValues(c)) ranks.set(r, (ranks.get(r) ?? 0) + 1);
    if (ranks.size) {
      facets.push({
        id: "rank",
        label: "Ranking",
        mode: "multi",
        options: [
          ...[...ranks.keys()].sort().map((r) => ({ value: r, label: r, test: (c: ConferenceOpportunity) => rankValues(c).includes(r) })),
          { value: "unranked", label: "Not ranked", test: (c: ConferenceOpportunity) => c.rank_badges.length === 0 },
        ],
      });
    }
    return facets;
  },
  sorts: [
    {
      value: "event",
      label: "Event date soonest",
      cmp: (a, b) => (a.event_date || "9999").localeCompare(b.event_date || "9999"),
    },
  ],
  detail: (c) => (
    <>
      <DetailSection title="When and where">
        <dl className="ws-dates">
          {c.event_dates ? (
            <div>
              <dt>Event</dt>
              <dd>{c.event_dates}</dd>
            </div>
          ) : null}
          {c.location || c.country ? (
            <div>
              <dt>Place</dt>
              <dd>{c.location && c.country && !c.location.includes(c.country) ? `${c.location}, ${c.country}` : c.location || c.country}</dd>
            </div>
          ) : null}
          {c.deadlines ? (
            <div>
              <dt>Deadlines</dt>
              <dd>{c.deadlines}</dd>
            </div>
          ) : null}
        </dl>
        <QualityWarningNote warnings={c.quality_warnings} />
      </DetailSection>
      {c.keywords ? (
        <DetailSection title="Topics">
          <p className="ws-meta-text">{c.keywords}</p>
        </DetailSection>
      ) : null}
    </>
  ),
  actionBar: (c) => ({ extraDeadlines: passedConferenceRounds(c.deadlines_structured, localToday()) }),
  primaryLink: "Conference site",
  emptyTitle: "Your conference matches are on their way",
  emptyDescription:
    "Once Mylo's nightly scan runs against your research profile, venues that fit — each with its submission deadline and why it fits — will appear here.",
};

const LAB_CONFERENCES_CONFIG: OpportunityFeedConfig<ConferenceOpportunity> = {
  ...CONFERENCES_CONFIG,
  emptyTitle: "No lab conference matches yet",
  emptyDescription: "Once Mylo has run for this lab, venues matched to its research will appear here.",
};

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
    <OpportunityFeed
      config={LAB_CONFERENCES_CONFIG}
      items={conferences}
      isLoading={isLoading}
      isError={isError}
      recommendedFor={data?.recommended_for}
      labName={lab.name}
    />
  );
}

function PersonalConferences() {
  const { data, isLoading, isError } = useConferences();
  const conferences = React.useMemo(() => data?.items ?? [], [data]);
  return <OpportunityFeed config={CONFERENCES_CONFIG} items={conferences} isLoading={isLoading} isError={isError} />;
}
