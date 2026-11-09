"use client";

import * as React from "react";
import {
  AlarmClock,
  Bookmark,
  CalendarDays,
  Check,
  CircleHelp,
  ExternalLink,
  EyeOff,
  MapPin,
  Megaphone,
  Minus,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import {
  memberOf,
  themeOf,
  type Check as CheckT,
  type FeedItem,
} from "@/components/labs/preview/fixtures";

export type Detail = { item: FeedItem };

type PreviewContextValue = {
  g: Record<string, OptionValue>;
  /** Open an item the way the "Opening an item" option says. */
  open: (item: FeedItem) => void;
  /** In "expand in place" mode, whether this item is the expanded one. */
  isExpanded: (id: string) => boolean;
};

export const PreviewContext = React.createContext<PreviewContextValue | null>(null);

export function usePreview() {
  const ctx = React.useContext(PreviewContext);
  if (!ctx) throw new Error("usePreview outside the Labs preview");
  return ctx;
}

/** Close a popover on outside click or Escape. */
export function useDismiss(open: boolean, close: () => void, ref: React.RefObject<HTMLElement | null>) {
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close, ref]);
}

/** A theme, named and colour-coded — colour is never the only signal. */
export function ThemeTag({ id, quiet = false }: { id: string; quiet?: boolean }) {
  const t = themeOf(id);
  return (
    <span
      className="lx-theme"
      data-quiet={quiet || undefined}
      style={{ "--tone": `var(--lx-tone-${t.tone})` } as React.CSSProperties}
    >
      <span className="lx-theme-dot" aria-hidden="true" />
      {t.label}
    </span>
  );
}

export function ThemeRow({ item }: { item: FeedItem }) {
  return (
    <span className="lx-theme-row">
      <ThemeTag id={item.theme} />
      {item.also.length ? (
        <span className="lx-meta-text" title={item.also.map((a) => themeOf(a).label).join(", ")}>
          Also {item.also.map((a) => themeOf(a).label).join(", ")}
        </span>
      ) : null}
    </span>
  );
}

/** A closing date in opportunity gold: the one place gold is spent. */
export function DeadlinePill({
  closesIn,
  closesOn,
  mode,
  prefix = "",
}: {
  closesIn: number;
  closesOn: string;
  mode: string;
  prefix?: string;
}) {
  if (closesIn < 0) {
    return (
      <span className="lx-deadline" data-closed>
        <AlarmClock size={13} aria-hidden="true" />
        Closed {closesOn}
      </span>
    );
  }
  const text =
    mode === "countdown"
      ? `${closesIn} days left`
      : mode === "date"
        ? `${prefix}${closesOn}`
        : `${prefix}${closesOn} · ${closesIn} days`;
  return (
    <span className="lx-deadline" data-soon={closesIn <= 14 || undefined}>
      <AlarmClock size={13} aria-hidden="true" />
      {text}
    </span>
  );
}

/** Save / remind / hide. Icon buttons with names; they do nothing in Labs. */
export function ItemActions({ item }: { item: FeedItem }) {
  const [saved, setSaved] = React.useState(item.saved);
  return (
    <div className="lx-actions">
      <button
        type="button"
        className="lx-icon-btn"
        aria-pressed={saved}
        aria-label={`${saved ? "Unsave" : "Save"} ${item.title}`}
        title={saved ? "Saved" : "Save"}
        onClick={(e) => {
          e.stopPropagation();
          setSaved((s) => !s);
        }}
      >
        <Bookmark size={15} fill={saved ? "currentColor" : "none"} aria-hidden="true" />
      </button>
      <button
        type="button"
        className="lx-icon-btn"
        aria-label={`Remind me about ${item.title}`}
        title="Remind me"
        onClick={(e) => e.stopPropagation()}
      >
        <AlarmClock size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        className="lx-icon-btn"
        aria-label={`Not for us: ${item.title}`}
        title="Not for us"
        onClick={(e) => e.stopPropagation()}
      >
        <EyeOff size={15} aria-hidden="true" />
      </button>
    </div>
  );
}

/** Mylo's portrait, small, riding a sentence he wrote. */
export function MyloMark({ size = 18 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static mascot art
    <img src="/mylo-portrait-64.webp" alt="" width={size} height={size} className="lx-mylo-mark" />
  );
}

export function Avatars({ ids, max = 3 }: { ids: string[]; max?: number }) {
  return (
    <span className="lx-avatars" aria-hidden="true">
      {ids.slice(0, max).map((id) => (
        <span key={id} className="lx-avatar-sm">
          {memberOf(id).initials}
        </span>
      ))}
    </span>
  );
}

/** "Best for Jun Park, Dr. Rosa Iglesias" — the lab-feed difference, on the card. */
export function BestFor({ item }: { item: FeedItem }) {
  if (item.suggested.length === 0) return null;
  const names = item.suggested.map((s) => memberOf(s.member).name.replace("Dr. ", ""));
  return (
    <span className="lx-bestfor">
      <Avatars ids={item.suggested.map((s) => s.member)} />
      <span>
        <span className="lx-bestfor-label">Best for</span> {names.join(", ")}
      </span>
    </span>
  );
}

const CHECK_WORD: Record<CheckT["status"], string> = {
  ok: "Yes",
  warn: "Check",
  unknown: "Unknown",
  block: "No",
};

function CheckGlyph({ status }: { status: CheckT["status"] }) {
  if (status === "ok") return <Check size={12} aria-hidden="true" />;
  if (status === "warn") return <TriangleAlert size={12} aria-hidden="true" />;
  if (status === "block") return <X size={12} aria-hidden="true" />;
  return <CircleHelp size={12} aria-hidden="true" />;
}

/** The compact form of the "Can we use this?" checks for a card. */
export function CheckChips({ checks }: { checks: CheckT[] }) {
  return (
    <ul className="lx-checks" aria-label="Can we use this?">
      {checks.map((c) => (
        <li key={c.label} data-status={c.status}>
          <CheckGlyph status={c.status} />
          <span className="lx-sr">{CHECK_WORD[c.status]}: </span>
          {c.label}
        </li>
      ))}
    </ul>
  );
}

/** The full checks for the detail view: a word, not only a colour, per row. */
function CheckTable({ checks }: { checks: CheckT[] }) {
  return (
    <ul className="lx-check-table">
      {checks.map((c) => (
        <li key={c.label} data-status={c.status}>
          <span className="lx-check-word">
            <CheckGlyph status={c.status} />
            {CHECK_WORD[c.status]}
          </span>
          <span>
            <span className="lx-check-label">{c.label}</span>
            {c.note ? <span className="lx-check-note">{c.note}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The line of facts under a card's title, by kind. */
function Facts({ item }: { item: FeedItem }) {
  switch (item.kind) {
    case "paper":
      return (
        <span className="lx-meta-text">
          {item.authors} · {item.venue} · {item.published}
        </span>
      );
    case "grant":
      return (
        <span className="lx-facts">
          <span className="lx-fact">{item.amount}</span>
          <span className="lx-meta-text">{item.program}</span>
        </span>
      );
    case "fellowship":
      return (
        <span className="lx-facts">
          <span className="lx-fact">{item.amount}</span>
          <span className="lx-meta-text">
            {item.stages.join(" / ")} · {item.citizenship === "us" ? "US citizens & residents" : "Any nationality"}
          </span>
        </span>
      );
    case "conference":
      return (
        <span className="lx-facts">
          <span className="lx-fact">
            <CalendarDays size={13} aria-hidden="true" /> {item.when}
          </span>
          <span className="lx-fact">
            <MapPin size={13} aria-hidden="true" /> {item.where}
          </span>
          {item.rank ? <span className="lx-pill">{item.rank}</span> : null}
        </span>
      );
  }
}

/** The signal at the top-left of a card: what this is and how urgent. */
function Signal({ item, deadline }: { item: FeedItem; deadline: string }) {
  switch (item.kind) {
    case "paper":
      return (
        <>
          <span className="lx-kind">{item.venue}</span>
          <span className="lx-meta-text">found {item.found}</span>
        </>
      );
    case "grant":
      return (
        <>
          <DeadlinePill closesIn={item.closesIn} closesOn={item.closesOn} mode={deadline} />
          <span className="lx-kind">{item.funder}</span>
        </>
      );
    case "fellowship":
      return (
        <>
          <DeadlinePill closesIn={item.closesIn} closesOn={item.closesOn} mode={deadline} />
          <span className="lx-kind">{item.sponsor}</span>
        </>
      );
    case "conference":
      return (
        <>
          {item.open ? (
            <DeadlinePill closesIn={item.closesIn} closesOn={item.closesOn} mode={deadline} prefix="Submit by " />
          ) : (
            <span className="lx-pill">Attend only</span>
          )}
          <span className="lx-kind">{item.acronym}</span>
        </>
      );
  }
}

/**
 * One item in a feed, as a card. No left gutter and no score: the signal
 * (deadline or venue) and actions on top, the title, Mylo's reason, the
 * caveat, then who it is for, its themes and its facts.
 */
export function FeedCard({
  item,
  show,
  deadline = "both",
  selected,
  onOpen,
}: {
  item: FeedItem;
  /** Which parts the "Each card shows" option keeps. */
  show: string[];
  deadline?: string;
  selected?: boolean;
  /** Replaces the default open behaviour (the reading pane selects instead). */
  onOpen?: () => void;
}) {
  const { open, isExpanded } = usePreview();
  const expanded = isExpanded(item.id);
  const has = (k: string) => show.includes(k);
  const checks = item.kind === "grant" || item.kind === "fellowship" ? item.checks : null;

  return (
    <article
      className="lx-item lx-card lx-rise"
      data-selected={selected || undefined}
      data-expanded={expanded || undefined}
      data-new={item.isNew || undefined}
    >
      <div className="lx-item-meta">
        <Signal item={item} deadline={deadline} />
        {item.isNew ? <span className="lx-new">New</span> : null}
        <ItemActions item={item} />
      </div>
      <h3 className="lx-item-title">
        <button
          type="button"
          onClick={() => (onOpen ? onOpen() : open(item))}
          aria-expanded={onOpen ? undefined : expanded}
          aria-current={selected || undefined}
        >
          {item.title}
        </button>
      </h3>
      {has("facts") ? <Facts item={item} /> : null}
      {has("reason") ? (
        <p className="lx-why">
          {item.byMylo ? <MyloMark /> : null}
          <span className="lx-clamp">
            <span className="lx-sr">{item.byMylo ? "Mylo's reason: " : "Why it matched: "}</span>
            {item.reason}
          </span>
        </p>
      ) : null}
      {has("caveat") ? (
        <p className="lx-caveat">
          <Minus size={13} aria-hidden="true" />
          <span>
            <span className="lx-sr">Might not be worth it: </span>
            {item.caveat}
          </span>
        </p>
      ) : null}
      {has("facts") && checks ? <CheckChips checks={checks} /> : null}
      {has("who") || has("themes") ? (
        <div className="lx-item-foot">
          {has("who") ? <BestFor item={item} /> : null}
          {has("themes") ? <ThemeRow item={item} /> : null}
        </div>
      ) : null}
      {expanded ? (
        <div className="lx-inline-detail">
          <ItemDetail item={item} embedded />
        </div>
      ) : null}
    </article>
  );
}

function Section({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="lx-detail-section">
      <h3 className="lx-detail-label">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * An opened item: in the reading pane, the side drawer, the dialog, or (in
 * "expand in place") under its card. Everything the card abbreviates is here
 * in full — Mylo's reasoning, who it is for and why, whether the lab can use
 * it, the dates, and where it came from.
 */
export function ItemDetail({ item, embedded = false }: { item: FeedItem; embedded?: boolean }) {
  const sourceLabel =
    item.kind === "paper" ? "Open paper" : item.kind === "conference" ? "Conference site" : "View call";

  return (
    <div className="lx-detail-body" data-embedded={embedded || undefined}>
      {embedded ? null : (
        <>
          <div className="lx-item-meta">
            <Signal item={item} deadline="both" />
          </div>
          <h2 className="lx-h lx-detail-title">{item.title}</h2>
          <Facts item={item} />
          <div className="lx-detail-actions">
            <a className="lx-btn lx-btn-solid" href="#" onClick={(e) => e.preventDefault()}>
              {sourceLabel} <ExternalLink size={13} aria-hidden="true" />
            </a>
            <button type="button" className="lx-btn lx-btn-line">
              <Bookmark size={13} aria-hidden="true" /> Save to Pulse Lab
            </button>
            <button type="button" className="lx-btn lx-btn-line">
              <AlarmClock size={13} aria-hidden="true" /> Remind
            </button>
          </div>
        </>
      )}

      <div className="lx-take">
        <div className="lx-take-head">
          {item.byMylo ? <MyloMark size={28} /> : null}
          <span>{item.byMylo ? "Mylo's take" : "Why it matched"}</span>
        </div>
        <p>{item.reason}</p>
        <p className="lx-take-caveat">
          <span className="lx-take-label">Why it might not</span>
          {item.caveat}
        </p>
      </div>

      {item.suggested.length ? (
        <Section title="Best suited to" icon={<Users size={13} aria-hidden="true" />}>
          <ul className="lx-people-why">
            {item.suggested.map((s) => {
              const m = memberOf(s.member);
              return (
                <li key={s.member}>
                  <span className="lx-avatar-sm lx-avatar-md" aria-hidden="true">
                    {m.initials}
                  </span>
                  <span>
                    <span className="lx-person">
                      {m.name} <span className="lx-meta-text">· {m.role}</span>
                    </span>
                    <span className="lx-person-why">{s.why}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : (
        <Section title="Best suited to" icon={<Users size={13} aria-hidden="true" />}>
          <p className="lx-meta-text">Nobody in the lab qualifies right now.</p>
        </Section>
      )}

      {item.kind === "grant" || item.kind === "fellowship" ? (
        <Section title="Can we use this?">
          <CheckTable checks={item.checks} />
        </Section>
      ) : null}

      {item.kind === "grant" ? (
        <Section title="Team fit">
          <p>{item.teamFit}</p>
        </Section>
      ) : null}

      {item.kind === "grant" || item.kind === "fellowship" || item.kind === "conference" ? (
        <Section title="Key dates" icon={<CalendarDays size={13} aria-hidden="true" />}>
          <dl className="lx-dates">
            {(item.kind === "conference" ? [...item.deadlines, { label: "Event", when: item.when }] : item.dates).map(
              (d) => (
                <div key={d.label}>
                  <dt>{d.label}</dt>
                  <dd>{d.when}</dd>
                </div>
              ),
            )}
          </dl>
        </Section>
      ) : null}

      {item.kind === "paper" ? (
        <Section title="Abstract">
          <p>{item.abstract}</p>
        </Section>
      ) : null}

      {item.projects.length ? (
        <Section title="Connects to">
          <div className="lx-chips lx-chips-wrap">
            {item.projects.map((p) => (
              <span key={p} className="lx-pill lx-pill-project">
                {p}
              </span>
            ))}
          </div>
        </Section>
      ) : null}

      <Section title="Themes">
        <ThemeRow item={item} />
      </Section>

      <p className="lx-source-row">
        <span>Source · {item.source}</span>
        {item.kind === "grant" && item.announced ? (
          <span>
            <Megaphone size={12} aria-hidden="true" /> Announced in {item.announced}
          </span>
        ) : null}
      </p>
    </div>
  );
}

export function PageHead({
  kicker,
  title,
  lede,
  children,
}: {
  kicker?: string;
  title: string;
  lede?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="lx-page-head lx-rise">
      <div>
        {kicker ? <p className="lx-kicker">{kicker}</p> : null}
        <h1 className="lx-h lx-page-title">{title}</h1>
        {lede ? <p className="lx-lede">{lede}</p> : null}
      </div>
      {children ? <div className="lx-page-tools">{children}</div> : null}
    </header>
  );
}
