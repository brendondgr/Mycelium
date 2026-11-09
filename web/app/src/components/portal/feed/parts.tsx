"use client";

import * as React from "react";
import { AlarmClock, Users } from "lucide-react";

import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import type { RecommendedMember } from "@/lib/portal/types";

/**
 * The pieces every feed card and opened item is built from — ported from the
 * `/labs` playground, where the layout was chosen. A feed maps its own rows
 * onto these; the save / remind / ignore controls, deadline menus and
 * usability checks stay the feed's own existing components, passed in as
 * slots, so nothing the cards could do before is lost.
 *
 * Every card, whatever its kind, has one skeleton (docs/styles.md): the match
 * on the left and the tools on the right, the title, one line saying where it
 * comes from (venue, funder, money), one line of who and when (authors and
 * year, or the deadline and posting), Mylo's reason on one line, then at most
 * three colour-coded themes with their share of the match. No position and no
 * verdict chip — the match is a measured similarity, never a model's guess.
 */

/** Mylo's painted portrait at text size — never the SVG rig. */
export function MyloMark({ size = 18 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static mascot art
    <img
      src="/mylo-portrait-64.webp"
      alt=""
      width={size}
      height={size}
      className="ws-mylo-mark"
    />
  );
}

/** A page's head: optional kicker, the serif title, a lede, and tools on the right. */
export function PageHead({
  kicker,
  title,
  lede,
  children,
}: {
  kicker?: React.ReactNode;
  title: React.ReactNode;
  lede?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="ws-page-head">
      <div className="min-w-0">
        {kicker ? <p className="ws-kicker">{kicker}</p> : null}
        <h1 className="ws-h ws-page-title">{title}</h1>
        {lede ? <p className="ws-lede">{lede}</p> : null}
      </div>
      {children ? <div className="ws-page-tools">{children}</div> : null}
    </header>
  );
}

export type ThemeRef = { id: string; label: string };

/** A theme, named and colour-coded — colour is never the only signal. */
export function ThemeTag({ theme }: { theme: ThemeRef }) {
  return (
    <span
      className="ws-theme"
      style={toneStyle(theme.id)}
    >
      <span className="ws-theme-dot" aria-hidden="true" />
      {theme.label}
    </span>
  );
}

/** The theme an item was matched to, then "Also …" for the others it reaches. */
export function ThemeRow({
  theme,
  also = [],
}: {
  theme: ThemeRef | null;
  also?: ThemeRef[];
}) {
  if (!theme && also.length === 0) return null;
  const alsoText = also.map((a) => a.label).join(", ");
  return (
    <span className="ws-theme-row">
      {theme ? <ThemeTag theme={theme} /> : null}
      {also.length ? (
        <span className="ws-meta-text" title={alsoText}>
          Also {alsoText}
        </span>
      ) : null}
    </span>
  );
}

/** A theme with its share of the match (null when there is no figure for it). */
export type ThemeMatch = ThemeRef & { pct: number | null };

/** The measured match an item carries: overall, and split by theme. */
export type MatchInfo = { overall: number | null; themes: ThemeMatch[] };

/**
 * The match a feed item states, from what the API serves.
 *
 * `embedding_match` is the real transformer cosine (0–100) between the item and
 * the reader's profile — the overall figure. `per_cluster` is each theme's
 * fusion score, which is *not* a percentage (it runs past 1), so a theme's
 * figure is the overall similarity scaled by how strongly that theme pulled the
 * item relative to the theme that pulled it most: the strongest theme reads the
 * overall figure, the others less. The breakdown says so in words.
 */
export function matchInfo(item: {
  embedding_match?: number | null;
  cluster?: ThemeRef | null;
  bridge_clusters?: ThemeRef[];
  per_cluster?: Record<string, number>;
}): MatchInfo {
  const overall = item.embedding_match ?? null;
  const refs: ThemeRef[] = [];
  for (const t of [item.cluster, ...(item.bridge_clusters ?? [])]) {
    if (t && !refs.some((r) => r.id === t.id)) refs.push(t);
  }
  const scores = item.per_cluster ?? {};
  const top = Math.max(0, ...refs.map((r) => scores[r.id] ?? 0));
  const themes = refs.map((r, i): ThemeMatch => {
    const score = scores[r.id];
    let pct: number | null = null;
    if (overall !== null && score !== undefined && top > 0) pct = Math.round((overall * score) / top);
    else if (overall !== null && i === 0) pct = overall;
    return { ...r, pct };
  });
  // Strongest first; the attributed theme wins a tie because it came first.
  themes.sort((a, b) => (b.pct ?? -1) - (a.pct ?? -1));
  return { overall, themes };
}

function toneStyle(id: string): React.CSSProperties {
  return { "--tone": `var(${clusterAccentVar(id)})` } as React.CSSProperties;
}

/** The themes as colour-coded pills with their share; one line on a card. */
export function TopicPills({ themes, max = 3 }: { themes: ThemeMatch[]; max?: number }) {
  if (!themes.length) return null;
  const shown = themes.slice(0, max);
  const rest = themes.length - shown.length;
  return (
    <ul className="ws-topics" aria-label="Themes it matched">
      {shown.map((t) => (
        <li
          key={t.id}
          className="ws-topic"
          style={toneStyle(t.id)}
          title={t.pct !== null ? `${t.label} · ${t.pct}%` : t.label}
        >
          <span className="ws-theme-dot" aria-hidden="true" />
          <span className="ws-topic-label">{t.label}</span>
          {t.pct !== null ? <span className="ws-topic-pct">{t.pct}%</span> : null}
        </li>
      ))}
      {rest > 0 ? (
        <li className="ws-topic ws-topic-more" title={themes.slice(max).map((t) => t.label).join(", ")}>
          +{rest}
        </li>
      ) : null}
    </ul>
  );
}

/**
 * The overall match as a ring and a figure, top-left on every card and opened
 * item. Hovering or focusing it opens the breakdown by theme.
 */
export function MatchBadge({
  match,
  byMylo = false,
  profile = "your research",
}: {
  match: MatchInfo;
  byMylo?: boolean;
  /** Whose profile the similarity is measured against. */
  profile?: string;
}) {
  const tipId = React.useId();
  if (match.overall === null) return null;
  const rows = match.themes.filter((t) => t.pct !== null);
  return (
    <span className="ws-match">
      <button type="button" className="ws-match-btn" aria-describedby={tipId}>
        <span
          className="ws-match-ring"
          style={{ "--p": match.overall } as React.CSSProperties}
          aria-hidden="true"
        />
        <span className="ws-match-num">{match.overall}%</span>
        <span className="ws-match-word">match</span>
      </button>
      <span className="ws-match-tip" role="tooltip" id={tipId}>
        <span className="ws-match-tip-head">
          {match.overall}% similar to {profile}
        </span>
        <span className="ws-match-tip-note">
          Embedding similarity between this item and {profile} — measured, not guessed.
        </span>
        {rows.length ? (
          <>
            <span className="ws-match-tip-label">By theme</span>
            {rows.map((t) => (
              <span key={t.id} className="ws-match-row" style={toneStyle(t.id)}>
                <span className="ws-match-row-name">
                  <span className="ws-theme-dot" aria-hidden="true" />
                  <span>{t.label}</span>
                </span>
                <span className="ws-match-bar" aria-hidden="true">
                  <i style={{ width: `${t.pct}%` }} />
                </span>
                <span className="ws-match-row-pct">{t.pct}%</span>
              </span>
            ))}
            {rows.length > 1 ? (
              <span className="ws-match-tip-note ws-match-tip-foot">
                Each theme scales the overall figure by how strongly it pulled this item.
              </span>
            ) : null}
          </>
        ) : null}
        <span className="ws-match-tip-foot">
          {byMylo
            ? "Mylo also read it and wrote a take."
            : "Matched by similarity; Mylo has not written a take."}
        </span>
      </span>
    </span>
  );
}

const DAY = 86_400_000;

/** Whole days from today to an ISO date (negative once it has passed). */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / DAY);
}

function shortDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * A closing date in opportunity gold — the one place gold is spent. Shows the
 * date and the days left; within two weeks it reads as urgent.
 */
export function DeadlinePill({
  date,
  prefix = "",
}: {
  date: string | null | undefined;
  prefix?: string;
}) {
  if (!date) return null;
  const days = daysUntil(date);
  if (days === null) return null;
  if (days < 0) {
    return (
      <span className="ws-deadline" data-closed>
        <AlarmClock size={13} aria-hidden="true" />
        Closed {shortDate(date)}
      </span>
    );
  }
  const left = days === 0 ? "today" : days === 1 ? "1 day" : `${days} days`;
  return (
    <span className="ws-deadline" data-soon={days <= 14 || undefined}>
      <AlarmClock size={13} aria-hidden="true" />
      {prefix}
      {shortDate(date)} · {left}
    </span>
  );
}

function firstName(name: string): string {
  return name.replace(/^Dr\.?\s+/, "");
}

/** "Best for Jun Park, Rosa Iglesias" — the lab-feed difference, on the card. */
export function BestFor({ members }: { members?: RecommendedMember[] }) {
  if (!members || members.length === 0) return null;
  return (
    <span className="ws-bestfor">
      <span className="ws-avatars" aria-hidden="true">
        {members.slice(0, 3).map((m) => (
          <span key={m.username} className="ws-avatar-sm">
            {m.initials}
          </span>
        ))}
      </span>
      <span>
        <span className="ws-bestfor-label">Best for</span>{" "}
        {members.map((m) => firstName(m.name)).join(", ")}
      </span>
    </span>
  );
}

/**
 * One item in a feed, as a card. The feed supplies the pieces; this decides
 * their order and look. The title is the button that opens the item (in the
 * reading pane on a wide screen, a drawer otherwise).
 */
export function FeedCard({
  title,
  match,
  isNew = false,
  flag,
  actions,
  source,
  meta,
  reason,
  byMylo = false,
  profile,
  extra,
  members,
  selected = false,
  onOpen,
}: {
  title: string;
  /** Top-left: the measured match; its breakdown opens on hover. */
  match: MatchInfo;
  isNew?: boolean;
  /** A small mark beside New (e.g. "Changed"). */
  flag?: React.ReactNode;
  /** Top-right: the feed's own remind / save / ignore controls. */
  actions?: React.ReactNode;
  /** One line under the title: where it comes from (venue, funder, money). */
  source?: React.ReactNode;
  /** One line under that: who and when (authors · year, deadline · posted). */
  meta?: React.ReactNode;
  reason?: string;
  byMylo?: boolean;
  profile?: string;
  /** Anything kind-specific worth a glance (check chips, a team-fit line). */
  extra?: React.ReactNode;
  members?: RecommendedMember[];
  selected?: boolean;
  onOpen: () => void;
}) {
  return (
    <article
      className="ws-item ws-rise"
      data-selected={selected || undefined}
      data-new={isNew || undefined}
    >
      <div className="ws-card-top">
        <MatchBadge match={match} byMylo={byMylo} profile={profile} />
        {isNew ? <span className="ws-new">New</span> : null}
        {flag}
        {actions ? <div className="ws-actions">{actions}</div> : null}
      </div>
      <h3 className="ws-item-title">
        <button
          type="button"
          onClick={onOpen}
          aria-current={selected || undefined}
        >
          {title}
        </button>
      </h3>
      {source || meta ? (
        <div className="ws-card-lines">
          {source ? <p className="ws-card-source">{source}</p> : null}
          {meta ? <p className="ws-card-meta">{meta}</p> : null}
        </div>
      ) : null}
      {reason ? (
        <p className="ws-why ws-why-line">
          {byMylo ? <MyloMark /> : null}
          <span className="ws-line-clamp">
            <span className="ws-sr">
              {byMylo ? "Mylo's reason: " : "Why it matched: "}
            </span>
            {reason}
          </span>
        </p>
      ) : null}
      {extra}
      <BestFor members={members} />
      <TopicPills themes={match.themes} />
    </article>
  );
}

export function DetailSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="ws-detail-section">
      <h3 className="ws-detail-label">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * An opened item, in the reading pane or the drawer. The same top row as its
 * card (match left, tools right), the title and its two lines, then one ruled
 * row holding the primary link (and, for a venue, its rankings) with the
 * deadline picker on the right; then every theme, Mylo's whole take with the
 * caveat, the About text straight after it, who in the lab it suits, the
 * kind-specific sections the feed passes as children, and where it came from.
 */
export function ItemDetail({
  title,
  match,
  isNew = false,
  tools,
  source,
  meta,
  primary,
  deadline,
  byMylo = false,
  profile,
  beats = [],
  reason,
  caveat,
  bridgeNote,
  about,
  aboutTitle = "About",
  members,
  showMembers = false,
  footer,
  children,
}: {
  title: string;
  match: MatchInfo;
  isNew?: boolean;
  /** Top-right: remind / save / ignore. */
  tools?: React.ReactNode;
  source?: React.ReactNode;
  meta?: React.ReactNode;
  /** The primary link, and anything that belongs level with it (rankings). */
  primary?: React.ReactNode;
  /** The deadline picker, at the right of the primary row. */
  deadline?: React.ReactNode;
  byMylo?: boolean;
  profile?: string;
  /** The reason's beats; falls back to `reason` when there are none. */
  beats?: string[];
  reason?: string;
  caveat?: string;
  bridgeNote?: string;
  /** The item's own description or abstract, shown right after Mylo's take. */
  about?: string;
  aboutTitle?: string;
  members?: RecommendedMember[];
  /** A lab feed shows "Best suited to" even when nobody qualifies. */
  showMembers?: boolean;
  footer?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const take = beats.filter(Boolean).length
    ? beats.filter(Boolean)
    : reason
      ? [reason]
      : [];
  return (
    <div className="ws-detail-body">
      <div className="ws-card-top">
        <MatchBadge match={match} byMylo={byMylo} profile={profile} />
        {isNew ? <span className="ws-new">New</span> : null}
        {tools ? <div className="ws-actions ws-actions-on">{tools}</div> : null}
      </div>
      <h2 className="ws-h ws-detail-title">{title}</h2>
      {source || meta ? (
        <div className="ws-card-lines ws-detail-lines">
          {source ? <p className="ws-card-source">{source}</p> : null}
          {meta ? <p className="ws-card-meta">{meta}</p> : null}
        </div>
      ) : null}

      {primary || deadline ? (
        <div className="ws-primary-row">
          {primary}
          {deadline ? <div className="ws-primary-deadline">{deadline}</div> : null}
        </div>
      ) : null}

      <TopicPills themes={match.themes} max={8} />

      {take.length || caveat ? (
        <div className="ws-take">
          <div className="ws-take-head">
            {byMylo ? <MyloMark size={28} /> : null}
            <span>{byMylo ? "Mylo's take" : "Why it matched"}</span>
          </div>
          {take.map((t, i) => (
            <p key={i}>{t}</p>
          ))}
          {bridgeNote ? <p className="ws-meta-text">{bridgeNote}</p> : null}
          {caveat ? (
            <p className="ws-take-caveat">
              <span className="ws-take-label">Why it might not</span>
              {caveat}
            </p>
          ) : null}
          {byMylo ? null : (
            <p className="ws-meta-text">
              Matched by similarity to the theme; Mylo has not written a
              judgement for it.
            </p>
          )}
        </div>
      ) : null}

      {about ? (
        <DetailSection title={aboutTitle}>
          <p>{about}</p>
        </DetailSection>
      ) : null}

      {members && members.length ? (
        <DetailSection
          title="Best suited to"
          icon={<Users size={13} aria-hidden="true" />}
        >
          <ul className="ws-people-why">
            {members.map((m) => (
              <li key={m.username}>
                <span className="ws-avatar-sm ws-avatar-md" aria-hidden="true">
                  {m.initials}
                </span>
                <span>
                  <span className="ws-person">{m.name}</span>
                  {m.reason ? (
                    <span className="ws-person-why">{m.reason}</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </DetailSection>
      ) : showMembers ? (
        <DetailSection
          title="Best suited to"
          icon={<Users size={13} aria-hidden="true" />}
        >
          <p className="ws-meta-text">
            Mylo has not matched this to anyone in the lab yet.
          </p>
        </DetailSection>
      ) : null}

      {children}

      {footer ? <div className="ws-source-row">{footer}</div> : null}
    </div>
  );
}
