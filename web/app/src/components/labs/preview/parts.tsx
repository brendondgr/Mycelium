"use client";

import * as React from "react";
import {
  AlarmClock,
  Bookmark,
  Check,
  CircleHelp,
  ExternalLink,
  EyeOff,
  Minus,
} from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import { themeOf, type Grant, type Paper } from "@/components/labs/preview/fixtures";

export type Detail = { kind: "paper"; item: Paper } | { kind: "grant"; item: Grant };

type PreviewContextValue = {
  g: Record<string, OptionValue>;
  /** Open an item the way the "Opening an item" option says. */
  open: (d: Detail) => void;
  /** In "expand in place" mode, whether this item is the expanded one. */
  isExpanded: (id: string) => boolean;
};

export const PreviewContext = React.createContext<PreviewContextValue | null>(null);

export function usePreview() {
  const ctx = React.useContext(PreviewContext);
  if (!ctx) throw new Error("usePreview outside the Labs preview");
  return ctx;
}

/** A theme, named and colour-coded — colour is never the only signal. */
export function ThemeTag({ id }: { id: string }) {
  const t = themeOf(id);
  return (
    <span className="lx-theme" style={{ "--tone": `var(--lx-tone-${t.tone})` } as React.CSSProperties}>
      <span className="lx-theme-dot" aria-hidden="true" />
      {t.label}
    </span>
  );
}

export function DeadlinePill({ grant, mode }: { grant: Grant; mode: string }) {
  const soon = grant.closesIn <= 14;
  const text =
    mode === "countdown"
      ? `${grant.closesIn} days left`
      : mode === "date"
        ? `Closes ${grant.closesOn}`
        : `${grant.closesOn} · ${grant.closesIn} days`;
  return (
    <span className="lx-deadline" data-soon={soon || undefined}>
      <AlarmClock size={13} aria-hidden="true" />
      {text}
    </span>
  );
}

/** Save / remind / hide. Icon buttons with names; they do nothing in Labs. */
export function ItemActions({ label }: { label: string }) {
  const [saved, setSaved] = React.useState(false);
  return (
    <div className="lx-actions">
      <button
        type="button"
        className="lx-icon-btn"
        aria-pressed={saved}
        aria-label={`${saved ? "Unsave" : "Save"} ${label}`}
        title={saved ? "Saved" : "Save"}
        onClick={(e) => {
          e.stopPropagation();
          setSaved((s) => !s);
        }}
      >
        <Bookmark size={15} fill={saved ? "currentColor" : "none"} aria-hidden="true" />
      </button>
      <button type="button" className="lx-icon-btn" aria-label={`Remind me about ${label}`} title="Remind me">
        <AlarmClock size={15} aria-hidden="true" />
      </button>
      <button type="button" className="lx-icon-btn" aria-label={`Not for us: ${label}`} title="Not for us">
        <EyeOff size={15} aria-hidden="true" />
      </button>
    </div>
  );
}

/** One paper in a feed. No left gutter, no score — title, theme, why, caveat. */
export function PaperItem({
  paper,
  summary,
  caveat,
  selected,
  compactTitle = false,
  onOpen,
}: {
  paper: Paper;
  summary: string;
  caveat: boolean;
  selected?: boolean;
  compactTitle?: boolean;
  /** Replaces the default open behaviour (the reading pane selects instead). */
  onOpen?: () => void;
}) {
  const { open, isExpanded } = usePreview();
  const expanded = isExpanded(paper.id);
  const full = summary === "full" || expanded;

  return (
    <article className="lx-item lx-rise" data-selected={selected || undefined} data-expanded={expanded || undefined}>
      <div className="lx-item-meta">
        <ThemeTag id={paper.theme} />
        <span className="lx-meta-text">
          {paper.venue} · found {paper.found}
        </span>
        <ItemActions label={paper.title} />
      </div>
      <h3 className="lx-item-title">
        <button
          type="button"
          onClick={() => (onOpen ? onOpen() : open({ kind: "paper", item: paper }))}
          aria-expanded={onOpen ? undefined : expanded}
          aria-current={selected || undefined}
        >
          {paper.title}
        </button>
      </h3>
      {compactTitle ? null : (
        <>
          <p className="lx-why">{paper.reason}</p>
          {caveat ? (
            <p className="lx-caveat">
              <Minus size={13} aria-hidden="true" />
              <span>
                <span className="lx-sr">Might not be worth it: </span>
                {paper.caveat}
              </span>
            </p>
          ) : null}
          {full ? (
            <p className="lx-abstract">
              <span className="lx-authors">{paper.authors}.</span> {paper.abstract}
            </p>
          ) : null}
          {expanded ? (
            <div className="lx-inline-actions">
              <a className="lx-btn lx-btn-solid" href="#" onClick={(e) => e.preventDefault()}>
                Open paper <ExternalLink size={13} aria-hidden="true" />
              </a>
            </div>
          ) : null}
        </>
      )}
    </article>
  );
}

export function CheckRow({ checks }: { checks: Grant["checks"] }) {
  return (
    <ul className="lx-checks" aria-label="Eligibility checks">
      {checks.map((c) => (
        <li key={c.label} data-ok={c.ok === null ? "unknown" : String(c.ok)}>
          {c.ok === true ? (
            <Check size={12} aria-hidden="true" />
          ) : c.ok === false ? (
            <Minus size={12} aria-hidden="true" />
          ) : (
            <CircleHelp size={12} aria-hidden="true" />
          )}
          <span className="lx-sr">{c.ok === true ? "Met: " : c.ok === false ? "Not met: " : "Unknown: "}</span>
          {c.label}
        </li>
      ))}
    </ul>
  );
}

export function GrantItem({
  grant,
  deadline,
  eligibility,
  amount,
}: {
  grant: Grant;
  deadline: string;
  eligibility: boolean;
  amount: boolean;
}) {
  const { open, isExpanded } = usePreview();
  const expanded = isExpanded(grant.id);
  return (
    <article className="lx-item lx-rise" data-expanded={expanded || undefined}>
      <div className="lx-item-meta">
        <DeadlinePill grant={grant} mode={deadline} />
        <span className="lx-meta-text">{grant.funder}</span>
        <ItemActions label={grant.title} />
      </div>
      <h3 className="lx-item-title">
        <button type="button" onClick={() => open({ kind: "grant", item: grant })} aria-expanded={expanded}>
          {grant.title}
        </button>
      </h3>
      <p className="lx-why">{grant.reason}</p>
      <div className="lx-item-foot">
        <ThemeTag id={grant.theme} />
        {amount ? <span className="lx-meta-text">{grant.amount}</span> : null}
      </div>
      {eligibility || expanded ? <CheckRow checks={grant.checks} /> : null}
    </article>
  );
}

/** The body of a paper or grant when opened in a drawer, dialog or pane. */
export function DetailBody({ detail }: { detail: Detail }) {
  if (detail.kind === "paper") {
    const p = detail.item;
    return (
      <div className="lx-detail-body">
        <ThemeTag id={p.theme} />
        <h2 className="lx-h lx-detail-title">{p.title}</h2>
        <p className="lx-meta-text">
          {p.authors} · {p.venue} · found {p.found}
        </p>
        <h3 className="lx-detail-label">Why it fits</h3>
        <p>{p.reason}</p>
        <h3 className="lx-detail-label">Why it might not</h3>
        <p>{p.caveat}</p>
        <h3 className="lx-detail-label">Abstract</h3>
        <p>{p.abstract}</p>
        <div className="lx-detail-actions">
          <a className="lx-btn lx-btn-solid" href="#" onClick={(e) => e.preventDefault()}>
            Open paper <ExternalLink size={13} aria-hidden="true" />
          </a>
          <button type="button" className="lx-btn lx-btn-line">
            <Bookmark size={13} aria-hidden="true" /> Save to Pulse Lab
          </button>
        </div>
      </div>
    );
  }
  const g = detail.item;
  return (
    <div className="lx-detail-body">
      <DeadlinePill grant={g} mode="both" />
      <h2 className="lx-h lx-detail-title">{g.title}</h2>
      <p className="lx-meta-text">
        {g.funder} · {g.amount}
      </p>
      <h3 className="lx-detail-label">Why it fits</h3>
      <p>{g.reason}</p>
      <h3 className="lx-detail-label">Can we apply?</h3>
      <CheckRow checks={g.checks} />
      <div className="lx-detail-actions">
        <a className="lx-btn lx-btn-solid" href="#" onClick={(e) => e.preventDefault()}>
          View call <ExternalLink size={13} aria-hidden="true" />
        </a>
        <button type="button" className="lx-btn lx-btn-line">
          <AlarmClock size={13} aria-hidden="true" /> Remind the lab
        </button>
      </div>
    </div>
  );
}

export function PageHead({ kicker, title, lede, children }: {
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
