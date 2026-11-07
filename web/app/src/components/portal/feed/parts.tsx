"use client";

import * as React from "react";
import { AlarmClock, Minus, Users } from "lucide-react";

import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import type { RecommendedMember } from "@/lib/portal/types";

/**
 * The pieces every feed card and opened item is built from — ported from the
 * `/labs` playground, where the layout was chosen. A feed maps its own rows
 * onto these; the save / remind / ignore controls, deadline menus and
 * usability checks stay the feed's own existing components, passed in as
 * slots, so nothing the cards could do before is lost.
 *
 * The card carries no percent, position or verdict (docs/styles.md): its
 * signal (venue or deadline), the title, Mylo's reason on one line with his
 * portrait, the caveat, then who it suits and its themes.
 */

/** Mylo's painted portrait at text size — never the SVG rig. */
export function MyloMark({ size = 18 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static mascot art
    <img src="/mylo-portrait-64.webp" alt="" width={size} height={size} className="ws-mylo-mark" />
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
    <span className="ws-theme" style={{ "--tone": clusterAccentVar(theme.id) } as React.CSSProperties}>
      <span className="ws-theme-dot" aria-hidden="true" />
      {theme.label}
    </span>
  );
}

/** The theme an item was matched to, then "Also …" for the others it reaches. */
export function ThemeRow({ theme, also = [] }: { theme: ThemeRef | null; also?: ThemeRef[] }) {
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
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/**
 * A closing date in opportunity gold — the one place gold is spent. Shows the
 * date and the days left; within two weeks it reads as urgent.
 */
export function DeadlinePill({ date, prefix = "" }: { date: string | null | undefined; prefix?: string }) {
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
        <span className="ws-bestfor-label">Best for</span> {members.map((m) => firstName(m.name)).join(", ")}
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
  signal,
  isNew = false,
  actions,
  facts,
  reason,
  byMylo = false,
  caveat,
  extra,
  members,
  theme,
  also,
  selected = false,
  onOpen,
}: {
  title: string;
  /** Top-left: the venue, or the deadline pill and the funder. */
  signal?: React.ReactNode;
  isNew?: boolean;
  /** Top-right: the feed's own save / remind / ignore controls. */
  actions?: React.ReactNode;
  facts?: React.ReactNode;
  reason?: string;
  byMylo?: boolean;
  caveat?: string;
  /** Anything kind-specific worth a glance (check chips, a team-fit line). */
  extra?: React.ReactNode;
  members?: RecommendedMember[];
  theme?: ThemeRef | null;
  also?: ThemeRef[];
  selected?: boolean;
  onOpen: () => void;
}) {
  const hasFoot = Boolean((members && members.length) || theme || (also && also.length));
  return (
    <article className="ws-item ws-rise" data-selected={selected || undefined} data-new={isNew || undefined}>
      <div className="ws-item-meta">
        {signal}
        {isNew ? <span className="ws-new">New</span> : null}
        {actions ? <div className="ws-actions">{actions}</div> : null}
      </div>
      <h3 className="ws-item-title">
        <button type="button" onClick={onOpen} aria-current={selected || undefined}>
          {title}
        </button>
      </h3>
      {facts}
      {reason ? (
        <p className="ws-why">
          {byMylo ? <MyloMark /> : null}
          <span className="ws-clamp">
            <span className="ws-sr">{byMylo ? "Mylo's reason: " : "Why it matched: "}</span>
            {reason}
          </span>
        </p>
      ) : null}
      {caveat ? (
        <p className="ws-caveat">
          <Minus size={13} aria-hidden="true" />
          <span>
            <span className="ws-sr">Might not be worth it: </span>
            {caveat}
          </span>
        </p>
      ) : null}
      {extra}
      {hasFoot ? (
        <div className="ws-item-foot">
          <BestFor members={members} />
          <ThemeRow theme={theme ?? null} also={also} />
        </div>
      ) : null}
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
 * An opened item, in the reading pane or the drawer. Everything the card
 * abbreviates is here in full: Mylo's whole reasoning and the caveat, who in
 * the lab it suits and why, then the kind-specific sections the feed passes as
 * children (can we use it, dates, abstract), its themes and where it came from.
 */
export function ItemDetail({
  title,
  signal,
  facts,
  actions,
  byMylo = false,
  beats = [],
  reason,
  caveat,
  bridgeNote,
  members,
  showMembers = false,
  theme,
  also,
  source,
  children,
}: {
  title: string;
  signal?: React.ReactNode;
  facts?: React.ReactNode;
  /** The primary link and the feed's own controls. */
  actions?: React.ReactNode;
  byMylo?: boolean;
  /** The reason's beats; falls back to `reason` when there are none. */
  beats?: string[];
  reason?: string;
  caveat?: string;
  bridgeNote?: string;
  members?: RecommendedMember[];
  /** A lab feed shows "Best suited to" even when nobody qualifies. */
  showMembers?: boolean;
  theme?: ThemeRef | null;
  also?: ThemeRef[];
  source?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const take = beats.filter(Boolean).length ? beats.filter(Boolean) : reason ? [reason] : [];
  return (
    <div className="ws-detail-body">
      {signal ? <div className="ws-item-meta">{signal}</div> : null}
      <h2 className="ws-h ws-detail-title">{title}</h2>
      {facts}
      {actions ? <div className="ws-detail-actions">{actions}</div> : null}

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
              Matched by similarity to the theme; Mylo has not written a judgement for it.
            </p>
          )}
        </div>
      ) : null}

      {members && members.length ? (
        <DetailSection title="Best suited to" icon={<Users size={13} aria-hidden="true" />}>
          <ul className="ws-people-why">
            {members.map((m) => (
              <li key={m.username}>
                <span className="ws-avatar-sm ws-avatar-md" aria-hidden="true">
                  {m.initials}
                </span>
                <span>
                  <span className="ws-person">{m.name}</span>
                  {m.reason ? <span className="ws-person-why">{m.reason}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </DetailSection>
      ) : showMembers ? (
        <DetailSection title="Best suited to" icon={<Users size={13} aria-hidden="true" />}>
          <p className="ws-meta-text">Mylo has not matched this to anyone in the lab yet.</p>
        </DetailSection>
      ) : null}

      {children}

      {theme || (also && also.length) ? (
        <DetailSection title="Themes">
          <ThemeRow theme={theme ?? null} also={also} />
        </DetailSection>
      ) : null}

      {source ? <div className="ws-source-row">{source}</div> : null}
    </div>
  );
}
