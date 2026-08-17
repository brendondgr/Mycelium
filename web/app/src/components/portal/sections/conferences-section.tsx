"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { RevealOnScroll } from "@/components/portal/motion/reveal-on-scroll";
import { MatchCard } from "@/components/portal/primitives/match-card";
import { MatchRing } from "@/components/portal/primitives/match-ring";
import { ClusterBadge } from "@/components/portal/primitives/cluster-badge";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { InfoPopover } from "@/components/portal/primitives/info-popover";
import {
  DeadlineRoundsButton,
  type DeadlineRound,
} from "@/components/portal/primitives/deadline-rounds";
import { SourceFooter } from "@/components/portal/primitives/source-footer";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CalendarIcon,
  CheckIcon,
  ConferenceIcon,
  ShieldIcon,
} from "@/components/portal/icons";
import {
  MyloReason,
  NewTag,
  RemindButton,
  SaveButton,
  deadlineLabel,
} from "@/components/portal/sections/opportunity-bits";
import {
  ConferenceFilters,
  DEFAULT_CONFERENCE_FILTERS,
  deriveConferenceFilterOptions,
  filterAndSortConferences,
  type ConferenceFilterState,
} from "@/components/portal/sections/conference-filters";
import { FeedSentinel } from "@/components/portal/primitives/feed-sentinel";
import {
  FeedSearchBar,
  clusterOptions,
  matchesQuery,
} from "@/components/portal/primitives/feed-search-bar";
import { usePortal } from "@/components/portal/portal-context";
import {
  useConferences,
  useLabRecommendations,
  useRankingReference,
} from "@/lib/portal/hooks";
import {
  revealDelay,
  useInfiniteReveal,
} from "@/lib/portal/use-infinite-reveal";
import { RecommendedFor } from "@/components/portal/primitives/recommended-for";
import type {
  ConferenceOpportunity,
  ConferenceRanking,
  MyLab,
  RankingReference,
  RecommendedMember,
  StructuredDeadline,
  TrustTier,
} from "@/lib/portal/types";

/** How many conferences each infinite-scroll slice reveals. */
const CONFERENCE_PAGE_SIZE = 24;

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
// Rank badges + trust tier (plan D2/D3) — the quality signals Pivot never had
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
 * itself a designed state: `TrustTierBadge` beside it is the signal that is
 * always present, so a card with no rank badges never reads as "no data". */
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
 * the same "authored on the client, backend only ships the fact" idiom
 * `TrustTierBadge`'s "unassigned" copy uses — these slugs have no reference-
 * table entry because they are heuristics, not a taxonomy the backend
 * maintains prose for. */
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
        None of these are conclusive on their own, and none of them remove
        this listing from your feed — they&rsquo;re just what Mylo noticed
        while reading it.
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

/** Both real tiers render with the identical token, weight, and shape — only
 * the letter differs — so the badge itself can never be read as "B is worse
 * than A". The hover copy (from the backend's reference table) is what
 * carries the actual meaning, and it says plainly that B is not a demotion:
 * it is where every non-CS venue lives, because the registry evidence layer
 * behind tier A only covers computing (plan D3). */
const TRUST_TIER_TOKEN = "--secondary";

/**
 * The always-present quality signal (plan D3): every resolved conference
 * series carries a trust tier, unlike the rank badges above which only ~25%
 * of series have — so this is the one quality badge every conference card
 * shows. "unassigned" — an instance whose resolve stage never matched it to a
 * series at all — gets a visually quieter, dashed treatment reading as
 * "no signal yet", not "poor": the backend's reference table doesn't cover it
 * (it isn't a real tier, just an absence), so its copy is authored here.
 */
function TrustTierBadge({ tier }: { tier: TrustTier }) {
  const referenceQuery = useRankingReference();

  if (tier === "unassigned") {
    return (
      <InfoPopover
        // Same WCAG 2.5.3 rule as `RankBadge` below: the visible pill reads
        // "No signal yet", so the accessible name must start with that exact
        // phrase, not bury it after "Trust tier not yet available".
        triggerLabel="No signal yet — trust tier not yet available"
        triggerClassName="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-dashed border-[var(--border)] px-2.5 py-1"
        trigger={
          <span className="text-xs font-semibold text-[var(--text-secondary)]">
            No signal yet
          </span>
        }
      >
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">
          Trust tier
        </p>
        <p className="mt-1.5">
          Mylo hasn&rsquo;t linked this listing to a known venue yet, so no
          independent evidence signal is available. This isn&rsquo;t a
          quality judgement — just nothing to report yet.
        </p>
      </InfoPopover>
    );
  }

  const label = tier === "A" ? "Tier A" : "Tier B";
  const explanation = referenceQuery.data?.trust_tiers[tier];

  return (
    <InfoPopover
      triggerLabel={`${label} — what this trust tier means`}
      triggerClassName="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1"
      triggerStyle={{
        borderColor: `color-mix(in srgb, var(${TRUST_TIER_TOKEN}) 55%, var(--border))`,
        backgroundColor: `color-mix(in srgb, var(${TRUST_TIER_TOKEN}) 30%, var(--surface))`,
      }}
      trigger={
        <>
          <ShieldIcon size={12} aria-hidden="true" />
          <span className="text-xs font-bold leading-none text-[var(--text-primary)]">
            {label}
          </span>
        </>
      }
    >
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">
        Trust tier {tier}
      </p>
      <p className="mt-1.5">
        {explanation ??
          (referenceQuery.isError
            ? "Couldn't load this tier's explanation right now."
            : "Loading…")}
      </p>
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

/** Every round of a conference's deadline list, sorted chronologically
 * (dated entries first, undated/unparseable ones — `instant === null` — last,
 * in their original order) and formatted for the hover. */
function conferenceDeadlineRounds(
  deadlines: StructuredDeadline[],
): DeadlineRound[] {
  const sorted = [...deadlines].sort((a, b) => {
    if (a.instant && b.instant) return a.instant.localeCompare(b.instant);
    if (a.instant) return -1;
    if (b.instant) return 1;
    return 0;
  });
  return sorted.map((deadline, index) => {
    const kindLabel =
      CONFERENCE_DEADLINE_KIND_LABELS[deadline.kind] ?? "Deadline";
    const label = deadline.round_label
      ? `${kindLabel} — ${deadline.round_label}`
      : kindLabel;
    return {
      key: `${deadline.kind}-${deadline.round_label}-${index}`,
      label,
      dateLabel: deadline.instant
        ? formatDeadlineInstant(deadline.instant)
        : deadline.raw || "Date TBD",
      estimated: deadline.is_estimated,
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
          backgroundColor: "color-mix(in srgb, var(--warning) 14%, var(--surface))",
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
}: {
  conf: ConferenceOpportunity;
  /** Set from a lab's Saves area so the reminder posts to that lab's channel. */
  remindLabSlug?: string;
  /** Lab-only: who Mylo judges this most applicable to. Personal feeds omit it. */
  recommendedFor?: RecommendedMember[];
}) {
  const where = conf.location || conf.country;
  // Use the semicolon-delimited subject categories, not the space-joined
  // `keywords` blob, so the tags render as real, separate chips.
  const subjects = conf.matched_subjects
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
  const shownSubjects = subjects.slice(0, 4);
  const moreSubjects = subjects.length - shownSubjects.length;

  return (
    <MatchCard
      ring={
        <MatchRing
          percent={conf.match_percent ?? conf.embedding_match}
          origin={conf.origin}
        />
      }
      head={
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {/* Title always first, so it lines up with the top of the ring
                  whether or not this conference has a cluster or a New tag. */}
              <h3 className="font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
                {conf.title}
              </h3>

              {/* Where and when sit with the title beside the ring — they
                  identify the event, the way a grant's sponsor line does. */}
              <dl className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
                {where ? (
                  <div className="flex gap-2">
                    <dt className="w-12 shrink-0 font-bold text-[var(--text-secondary)]">
                      Where
                    </dt>
                    <dd className="min-w-0">{where}</dd>
                  </div>
                ) : null}
                {conf.event_dates ? (
                  <div className="flex gap-2">
                    <dt className="w-12 shrink-0 font-bold text-[var(--text-secondary)]">
                      When
                    </dt>
                    <dd>{conf.event_dates}</dd>
                  </div>
                ) : null}
              </dl>

              {/* Trust tier renders unconditionally (plan D3: every resolved
                  series has one — it is the always-present quality signal).
                  Rank badges follow it, when the series has any (~25%). */}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {conf.is_new ? <NewTag /> : null}
                {conf.cluster ? <ClusterBadge cluster={conf.cluster} /> : null}
                <TrustTierBadge tier={conf.trust_tier} />
                <RankBadgeRow badges={conf.rank_badges} />
                <RedFlagsBadge flags={conf.red_flags} />
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              <RemindButton
                contentId={conf.content_id}
                title={conf.title}
                deadlines={conf.addressable_deadlines}
                lockedLabSlug={remindLabSlug}
              />
              <SaveButton
                contentId={conf.content_id}
                saved={conf.saved}
                savedLabs={conf.saved_labs}
              />
            </div>
          </div>
        </>
      }
    >
      {conf.deadline_date ? (
        <DeadlineRoundsButton
          triggerClassName="mt-2.5 inline-flex"
          triggerLabel={`${deadlineLabel(conf.deadline_kind, conf.deadline_date)} — see every submission round`}
          trigger={
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--destructive)]">
              <CalendarIcon size={15} aria-hidden="true" />
              {deadlineLabel(conf.deadline_kind, conf.deadline_date)}
              {conf.deadlines_structured.length > 1 ? (
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  · {conf.deadlines_structured.length} rounds
                </span>
              ) : null}
            </span>
          }
          rounds={
            conf.deadlines_structured.length > 0
              ? conferenceDeadlineRounds(conf.deadlines_structured)
              : [
                  {
                    key: "next",
                    label:
                      CONFERENCE_DEADLINE_KIND_LABELS[conf.deadline_kind] ??
                      "Deadline",
                    dateLabel: formatDeadlineInstant(conf.deadline_date),
                  },
                ]
          }
        />
      ) : null}

      {/* Directly beneath the deadline it qualifies — see `QualityWarningNote`
          above for why this can't sit anywhere quieter than that. */}
      <QualityWarningNote warnings={conf.quality_warnings} />

      {/* The venue's own blurb, when the listing carries one (many don't). */}
      {conf.description ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          {conf.description}
        </p>
      ) : null}

      {/* What's still accepting — the open submission windows for this venue. */}
      {conf.abstract_open || conf.manuscript_open ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {conf.abstract_open ? <OpenChip label="Abstract open" /> : null}
          {conf.manuscript_open ? <OpenChip label="Full paper open" /> : null}
        </div>
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

      {shownSubjects.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {shownSubjects.map((subject) => (
            <span
              key={subject}
              className="rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              {subject}
            </span>
          ))}
          {moreSubjects > 0 ? (
            <span className="px-1 text-xs font-medium text-[var(--text-secondary)]">
              +{moreSubjects} more
            </span>
          ) : null}
        </div>
      ) : null}

      <RecommendedFor members={recommendedFor} />

      <SourceFooter
        license={conf.license}
        licenseUrl={conf.license_url}
        sourceLinks={conf.source_links}
        source={conf.source}
      />

      {conf.url ? (
        <a
          href={conf.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          View conference
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

function CardSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-6 w-24 rounded-full bg-surface-alt" />
        <span className="h-6 w-20 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/2 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
    </Card>
  );
}

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * The Conferences page: calls for papers matched to the researcher, in
 * recommendation order, one card per row like Papers / Grants / Fellowships
 * (percent match and any "New" tag lead each card). A left-hand filter rail
 * (submission status, abstract/paper open,
 * deadline & event-date windows, continent, country, subject, new/saved, sort)
 * narrows the already-fetched feed in memory — instant, no refetch. The results
 * scroll infinitely, revealing a slice at a time as the reader nears the bottom,
 * matching the Grants / Fellowships pattern.
 */
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
    <ConferencesFeed
      conferences={conferences}
      isLoading={isLoading}
      isError={isError}
      generatedAt={data?.generated_at ?? null}
      recommendedFor={data?.recommended_for}
      labName={lab.name}
    />
  );
}

function PersonalConferences() {
  const { data, isLoading, isError } = useConferences();
  const conferences = React.useMemo(() => data?.items ?? [], [data]);
  return (
    <ConferencesFeed
      conferences={conferences}
      isLoading={isLoading}
      isError={isError}
      generatedAt={data?.generated_at ?? null}
    />
  );
}

/**
 * The shared Conferences feed body — the keyword search and cluster chips at the
 * top, the filter rail, infinite-scroll card list,
 * and end-of-feed marker — used identically by the personal page and a lab workspace. `labName`, when
 * set, marks the lab variant and only swaps the surrounding copy; the structure,
 * filters, and card layout are the same in both.
 */
function ConferencesFeed({
  conferences,
  isLoading,
  isError,
  generatedAt,
  recommendedFor,
  labName,
}: {
  conferences: ConferenceOpportunity[];
  isLoading: boolean;
  isError: boolean;
  generatedAt: string | null;
  /** Lab-only: content id → the members Mylo judges each conference is for. */
  recommendedFor?: Record<string, RecommendedMember[]>;
  labName?: string;
}) {
  const [filters, setFilters] = React.useState<ConferenceFilterState>(
    DEFAULT_CONFERENCE_FILTERS,
  );
  const [query, setQuery] = React.useState("");
  const [selectedCluster, setSelectedCluster] = React.useState<string | null>(
    null,
  );

  const clusters = React.useMemo(
    () => clusterOptions(conferences),
    [conferences],
  );

  // The top-of-page search and cluster chips scope the feed first; the rail's
  // facets then narrow whatever that scope left, so its counts read against the
  // theme the reader is looking at rather than the whole run.
  const scoped = React.useMemo(() => {
    const needle = query.trim();
    if (!needle && !selectedCluster) return conferences;
    return conferences.filter((conf) => {
      if (selectedCluster && conf.cluster?.id !== selectedCluster) return false;
      return matchesQuery(
        [
          conf.title,
          conf.description,
          conf.reason,
          conf.location,
          conf.matched_subjects,
        ],
        needle,
      );
    });
  }, [conferences, query, selectedCluster]);

  const options = React.useMemo(
    () => deriveConferenceFilterOptions(scoped),
    [scoped],
  );
  const today = React.useMemo(() => new Date().toISOString().slice(0, 10), []);
  const visible = React.useMemo(
    () => filterAndSortConferences(scoped, filters, today),
    [scoped, filters, today],
  );

  const clearAll = () => {
    setFilters(DEFAULT_CONFERENCE_FILTERS);
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
    useInfiniteReveal(visible, CONFERENCE_PAGE_SIZE, resetKey);

  const showRail = !isLoading && !isError && conferences.length > 0;

  const subtitle: React.ReactNode = (() => {
    if (isLoading) {
      return labName
        ? `Gathering conferences that fit ${labName}…`
        : "Gathering conferences that fit your work…";
    }
    if (conferences.length > 0) {
      const when = formatWhen(generatedAt);
      const count = `${conferences.length} conference${
        conferences.length === 1 ? "" : "s"
      }`;
      const lead = labName
        ? `${count}, matched to ${labName}`
        : `${count}, ranked by fit`;
      return when ? `${lead} · gathered ${when}.` : `${lead}.`;
    }
    return labName
      ? `Conferences and calls for papers matched to ${labName}, best fit first.`
      : "Conferences and calls for papers matched to your research, best fit first.";
  })();

  return (
    <div>
      <SectionHeader
        eyebrow="Opportunities"
        title="Conferences"
        subtitle={subtitle}
      />

      {conferences.length > 0 && !isLoading && !isError ? (
        <FeedSearchBar
          query={query}
          onQueryChange={setQuery}
          placeholder="Search conferences by title, location, or subject…"
          clusters={clusters}
          selectedCluster={selectedCluster}
          onClusterChange={setSelectedCluster}
        />
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
        {showRail ? (
          <ConferenceFilters
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
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              title={
                labName
                  ? "Couldn't load this feed"
                  : "Couldn't load your conferences"
              }
              description={
                labName
                  ? "Something went wrong loading the lab's conference matches. Please try again in a moment."
                  : "Something went wrong fetching your conference matches. Please try again in a moment."
              }
            />
          ) : conferences.length === 0 ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              badge={labName ? undefined : "Coming soon"}
              title={
                labName
                  ? "No lab conference matches yet"
                  : "Your conference matches are on their way"
              }
              description={
                labName
                  ? "Once Mylo has run for this lab, conferences and calls for papers matching its purpose will appear here."
                  : "Once Mylo's nightly scan of calls for papers runs against your research profile, the venues that best fit your work — each with a percent match and its submission deadline — will appear here as cards."
              }
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<ConferenceIcon size={28} />}
              title="No conferences match these filters"
              description="Try a different search term, another cluster, or widen your filters to see more of your matched conferences."
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
              <div className="space-y-3.5">
                {displayed.map((conf, index) => (
                  <RevealOnScroll
                    key={conf.content_id}
                    delay={revealDelay(index, CONFERENCE_PAGE_SIZE, 45)}
                  >
                    <ConferenceCard
                      conf={conf}
                      recommendedFor={recommendedFor?.[conf.content_id]}
                    />
                  </RevealOnScroll>
                ))}
              </div>
              <FeedSentinel
                sentinelRef={sentinelRef}
                hasMore={hasMore}
                remaining={remaining}
                onRevealMore={revealMore}
                totalShown={displayed.length}
                noun="conferences"
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
