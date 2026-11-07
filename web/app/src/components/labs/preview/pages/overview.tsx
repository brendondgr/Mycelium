"use client";

import * as React from "react";
import { ArrowRight, Download, FileText, Search } from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import {
  FEEDS,
  FOUND,
  KIND_LABEL,
  MEMBERS,
  MYLO_ASKS,
  PROJECTS,
  THEMES,
  allItems,
  type FeedItem,
  type FeedKind,
  type Scope,
} from "@/components/labs/preview/fixtures";
import { BestFor, DeadlinePill, MyloMark, PageHead, ThemeTag, usePreview } from "@/components/labs/preview/parts";

function Panel({
  title,
  action,
  onAction,
  children,
  className = "",
}: {
  title: string;
  action?: string;
  onAction?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`lx-panel-box lx-rise ${className}`} aria-label={title}>
      <div className="lx-panel-head">
        <h2 className="lx-h lx-panel-title">{title}</h2>
        {action ? (
          <button type="button" className="lx-link" onClick={onAction}>
            {action} <ArrowRight size={13} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {children}
    </section>
  );
}

/** Mylo's reason on one line with his portrait — never stacked above it. */
function Reason({ item }: { item: FeedItem }) {
  return (
    <p className="lx-compact-why">
      {item.byMylo ? <MyloMark size={16} /> : null}
      <span className="lx-clamp">{item.reason}</span>
    </p>
  );
}

function MyloNote({ scope }: { scope: Scope }) {
  return (
    <section className="lx-note lx-rise" aria-label="Mylo's note">
      {/* eslint-disable-next-line @next/next/no-img-element -- static mascot art */}
      <img src="/mylo-portrait-128.webp" alt="" width={44} height={44} className="lx-note-mylo" />
      <div>
        <p className="lx-note-text">
          I found <strong>12 papers</strong> relevant to {scope.kind === "personal" ? "your" : `${scope.name}'s`}{" "}
          themes overnight. Two strengthen the triage-agent write-up, Ama qualifies for the NSF fellowship closing in{" "}
          <strong className="lx-gold">13 days</strong>, and the NIH clinical-AI letter of intent is due in{" "}
          <strong className="lx-gold">9 days</strong>.
        </p>
        <button type="button" className="lx-link">
          Read this morning&apos;s report <ArrowRight size={13} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

const REPORT_ROWS: { kind: FeedKind; area: string; fresh: number }[] = [
  { kind: "paper", area: "Papers", fresh: 12 },
  { kind: "grant", area: "Grants", fresh: 3 },
  { kind: "fellowship", area: "Fellowships", fresh: 2 },
  { kind: "conference", area: "Conferences", fresh: 2 },
];

/** The morning report at a glance: one row per area, its lead item, a way in. */
function Report() {
  const { open } = usePreview();
  return (
    <Panel title="This morning's report" action="Open report">
      <table className="lx-table lx-report">
        <thead>
          <tr>
            <th scope="col">Area</th>
            <th scope="col">New</th>
            <th scope="col">Leading item</th>
          </tr>
        </thead>
        <tbody>
          {REPORT_ROWS.map((r) => {
            const lead = FEEDS[r.kind].find((i) => i.isNew) ?? FEEDS[r.kind][0];
            return (
              <tr key={r.kind}>
                <th scope="row">{r.area}</th>
                <td>{r.fresh}</td>
                <td>
                  <button type="button" className="lx-compact-title lx-report-lead" onClick={() => open(lead)}>
                    {lead.title}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="lx-panel-foot">
        <span className="lx-meta-text">Written 06:02 · 19 items across 4 themes</span>
        <button type="button" className="lx-link">
          <Download size={13} aria-hidden="true" /> PDF
        </button>
      </div>
    </Panel>
  );
}

function Found() {
  return (
    <Panel title="What Mylo found">
      <table className="lx-table">
        <thead>
          <tr>
            <th scope="col">Area</th>
            <th scope="col">Today</th>
            <th scope="col">Week</th>
          </tr>
        </thead>
        <tbody>
          {FOUND.map((f) => (
            <tr key={f.key}>
              <th scope="row">{f.label}</th>
              <td>{f.today}</td>
              <td>{f.week}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function FoundInline({ mode }: { mode: string }) {
  if (mode === "strip") {
    return (
      <p className="lx-found-strip lx-rise">
        <span className="lx-found-label">Today</span>
        {FOUND.map((f) => (
          <span key={f.key} className="lx-found-chip">
            <strong>{f.today}</strong> {f.label}
          </span>
        ))}
        <span className="lx-meta-text">· 85 this week</span>
      </p>
    );
  }
  return (
    <div className="lx-tiles lx-rise">
      {FOUND.map((f) => (
        <div key={f.key} className="lx-tile">
          <span className="lx-tile-num">{f.today}</span>
          <span className="lx-tile-label">{f.label} today</span>
          <span className="lx-meta-text">{f.week} this week</span>
        </div>
      ))}
    </div>
  );
}

/** Every kind of item, grouped under the theme it was matched to. */
function TodayByTheme({ perTheme }: { perTheme: number }) {
  const { open } = usePreview();
  const items = allItems();
  return (
    <Panel title="Today, by theme" action="All feeds" className="lx-span-main">
      <div className="lx-theme-groups">
        {THEMES.map((t) => {
          const fresh = items.filter((i) => i.theme === t.id && i.isNew);
          if (fresh.length === 0) return null;
          return (
            <div key={t.id} className="lx-theme-group">
              <div className="lx-theme-group-head">
                <ThemeTag id={t.id} />
                <span className="lx-meta-text">{fresh.length} new</span>
              </div>
              <ul className="lx-compact-list">
                {fresh.slice(0, perTheme).map((i) => (
                  <li key={i.id}>
                    <span className="lx-row-kind">
                      <span className="lx-kind-chip">{KIND_LABEL[i.kind]}</span>
                      {"closesIn" in i && i.closesIn >= 0 ? (
                        <DeadlinePill closesIn={i.closesIn} closesOn={i.closesOn} mode="both" />
                      ) : null}
                    </span>
                    <button type="button" className="lx-compact-title" onClick={() => open(i)}>
                      {i.title}
                    </button>
                    <Reason item={i} />
                    <BestFor item={i} />
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function ClosingSoon({ deadline }: { deadline: string }) {
  const { open } = usePreview();
  const soon = allItems()
    .flatMap((i) => ("closesIn" in i && i.closesIn >= 0 && i.closesIn <= 30 ? [i] : []))
    .sort((a, b) => a.closesIn - b.closesIn);
  return (
    <Panel title="Closing soon" action="Deadlines">
      <ul className="lx-compact-list">
        {soon.map((i) => (
          <li key={i.id}>
            <span className="lx-row-kind">
              <DeadlinePill closesIn={i.closesIn} closesOn={i.closesOn} mode={deadline} />
              <span className="lx-meta-text">{KIND_LABEL[i.kind]}</span>
            </span>
            <button type="button" className="lx-compact-title" onClick={() => open(i)}>
              {i.title}
            </button>
            <BestFor item={i} />
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** Per person: how much Mylo set aside for them, and the one to read first. */
function ForEachPerson() {
  const { open } = usePreview();
  const items = allItems();
  return (
    <Panel title="For each person" action="Members">
      <ul className="lx-person-list">
        {MEMBERS.map((m) => {
          const theirs = items.filter((i) => i.suggested.some((s) => s.member === m.id));
          const first = theirs.find((i) => i.isNew) ?? theirs[0];
          return (
            <li key={m.id}>
              <span className="lx-avatar-sm lx-avatar-md" aria-hidden="true">
                {m.initials}
              </span>
              <span className="lx-person-body">
                <span className="lx-person">
                  {m.name} <span className="lx-meta-text">· {theirs.length} for them</span>
                </span>
                {first ? (
                  <button type="button" className="lx-person-first" onClick={() => open(first)}>
                    Start with: {first.title}
                  </button>
                ) : (
                  <span className="lx-meta-text">Nothing new for them today.</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function MyloAsks() {
  const [answered, setAnswered] = React.useState<Record<string, string>>({});
  return (
    <Panel title="Mylo is asking" action="Mylo & you">
      <ul className="lx-asks">
        {MYLO_ASKS.map((a) => (
          <li key={a.id}>
            <p className="lx-ask-q">
              <MyloMark size={18} />
              <span>{a.question}</span>
            </p>
            <p className="lx-meta-text">{a.context}</p>
            {answered[a.id] ? (
              <p className="lx-ask-done" role="status">
                Noted: {answered[a.id]}.
              </p>
            ) : (
              <div className="lx-ask-actions">
                {a.answers.map((ans, n) => (
                  <button
                    key={ans}
                    type="button"
                    className={`lx-btn ${n === 0 ? "lx-btn-solid" : "lx-btn-line"} lx-btn-sm`}
                    onClick={() => setAnswered((prev) => ({ ...prev, [a.id]: ans }))}
                  >
                    {ans}
                  </button>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ProjectPulse() {
  return (
    <Panel title="Project pulse" action="Projects">
      <ul className="lx-compact-list">
        {PROJECTS.map((p) => (
          <li key={p.id} className="lx-project">
            <span className="lx-compact-title lx-static">{p.name}</span>
            <span className="lx-pill">{p.status}</span>
            <p className="lx-compact-why">{p.moved}</p>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function OverviewPage({
  o,
  scope,
  deadline,
  go,
}: {
  o: Record<string, OptionValue>;
  scope: Scope;
  /** The feeds' date format, so a deadline reads the same everywhere. */
  deadline: string;
  go: (key: string) => void;
}) {
  const sections = o.sections as string[];
  const has = (k: string) => sections.includes(k);
  const perTheme = Number(o.perTheme);
  const layout = o.layout as string;
  const statsMode = o.stats as string;

  const main = (
    <>
      {has("report") ? <Report /> : null}
      {has("today") ? <TodayByTheme perTheme={perTheme} /> : null}
    </>
  );
  const side = (
    <>
      {has("closing") ? <ClosingSoon deadline={deadline} /> : null}
      {has("people") ? <ForEachPerson /> : null}
      {has("asks") ? <MyloAsks /> : null}
      {has("projects") ? <ProjectPulse /> : null}
      {has("found") && statsMode === "table" ? <Found /> : null}
    </>
  );

  return (
    <div className="lx-overview" data-layout={layout}>
      <PageHead
        kicker="Saturday, 7 November"
        title={scope.kind === "personal" ? "Good morning." : scope.name}
        lede={
          scope.kind === "personal"
            ? "Here is what changed in your field overnight."
            : "What changed in the lab's field overnight, and who it is for."
        }
      >
        <button type="button" className="lx-btn lx-btn-solid">
          <FileText size={14} aria-hidden="true" /> Today&apos;s report
        </button>
        <button type="button" className="lx-btn lx-btn-line" onClick={() => go("search")}>
          <Search size={14} aria-hidden="true" /> Search
        </button>
      </PageHead>
      {has("note") ? <MyloNote scope={scope} /> : null}
      {has("found") && statsMode !== "table" ? <FoundInline mode={statsMode} /> : null}

      {layout === "split" ? (
        <div className="lx-split">
          <div className="lx-split-main">{main}</div>
          <div className="lx-split-side">{side}</div>
        </div>
      ) : layout === "bento" ? (
        <div className="lx-bento">
          {main}
          {side}
        </div>
      ) : (
        <div className="lx-stack">
          {main}
          {side}
        </div>
      )}
    </div>
  );
}
