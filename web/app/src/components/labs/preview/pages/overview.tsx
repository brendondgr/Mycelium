"use client";

import * as React from "react";
import { ArrowRight } from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import {
  FELLOWSHIPS,
  FOUND,
  GRANTS,
  PAPERS,
  PROJECTS,
  THEMES,
  type Scope,
} from "@/components/labs/preview/fixtures";
import { BestFor, DeadlinePill, MyloMark, PageHead, ThemeTag, usePreview } from "@/components/labs/preview/parts";

function Panel({ title, action, children, className = "" }: {
  title: string;
  action?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`lx-panel-box lx-rise ${className}`} aria-label={title}>
      <div className="lx-panel-head">
        <h2 className="lx-h lx-panel-title">{title}</h2>
        {action ? (
          <button type="button" className="lx-link">
            {action} <ArrowRight size={13} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function MyloNote({ scope }: { scope: Scope }) {
  return (
    <section className="lx-note lx-rise" aria-label="Mylo's note">
      {/* eslint-disable-next-line @next/next/no-img-element -- static mascot art */}
      <img src="/mylo-portrait-128.webp" alt="" width={44} height={44} className="lx-note-mylo" />
      <div>
        <p className="lx-note-text">
          I found <strong>12 papers</strong> relevant to {scope.kind === "personal" ? "your" : `${scope.name}'s`} themes
          overnight. Two strengthen the triage-agent write-up, and the NIH clinical-AI call closes in{" "}
          <strong className="lx-gold">9 days</strong>.
        </p>
        <button type="button" className="lx-link">
          Read this morning&apos;s report <ArrowRight size={13} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

function Found({ mode }: { mode: string }) {
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
  if (mode === "tiles") {
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

function TodayByTheme({ perTheme }: { perTheme: number }) {
  const { open } = usePreview();
  return (
    <Panel title="Today, by theme" action="All papers" className="lx-span-main">
      <div className="lx-theme-groups">
        {THEMES.map((t) => {
          const items = PAPERS.filter((p) => p.theme === t.id).slice(0, perTheme);
          if (items.length === 0) return null;
          return (
            <div key={t.id} className="lx-theme-group">
              <ThemeTag id={t.id} />
              <ul className="lx-compact-list">
                {items.map((p) => (
                  <li key={p.id}>
                    <button type="button" className="lx-compact-title" onClick={() => open(p)}>
                      {p.title}
                    </button>
                    <p className="lx-compact-why">
                      {p.byMylo ? <MyloMark size={16} /> : null}
                      {p.reason}
                    </p>
                    <BestFor item={p} />
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
  return (
    <Panel title="Closing soon" action="All deadlines">
      <ul className="lx-compact-list">
        {[...GRANTS, ...FELLOWSHIPS]
          .filter((g) => g.closesIn <= 30)
          .sort((a, b) => a.closesIn - b.closesIn)
          .map((g) => (
          <li key={g.id}>
            <DeadlinePill closesIn={g.closesIn} closesOn={g.closesOn} mode={deadline} />
            <button type="button" className="lx-compact-title" onClick={() => open(g)}>
              {g.title}
            </button>
            <p className="lx-meta-text">{g.kind === "grant" ? g.funder : `${g.sponsor} · fellowship`}</p>
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
}: {
  o: Record<string, OptionValue>;
  scope: Scope;
  /** The grants page's deadline format, so a deadline reads the same everywhere. */
  deadline: string;
}) {
  const sections = o.sections as string[];
  const has = (k: string) => sections.includes(k);
  const perTheme = Number(o.perTheme);
  const layout = o.layout as string;
  const statsMode = o.stats as string;

  const side = (
    <>
      {has("found") && statsMode === "table" ? <Found mode="table" /> : null}
      {has("closing") ? <ClosingSoon deadline={deadline} /> : null}
      {has("projects") ? <ProjectPulse /> : null}
    </>
  );

  return (
    <div className="lx-overview" data-layout={layout}>
      <PageHead
        kicker="Saturday, 7 November"
        title={scope.kind === "personal" ? "Good morning." : scope.name}
        lede={scope.kind === "personal" ? "Here is what changed in your field overnight." : "What changed in the lab's field overnight."}
      />
      {has("note") ? <MyloNote scope={scope} /> : null}
      {has("found") && statsMode !== "table" ? <Found mode={statsMode} /> : null}

      {layout === "split" ? (
        <div className="lx-split">
          <div className="lx-split-main">{has("today") ? <TodayByTheme perTheme={perTheme} /> : null}</div>
          <div className="lx-split-side">{side}</div>
        </div>
      ) : layout === "bento" ? (
        <div className="lx-bento">
          {has("today") ? <TodayByTheme perTheme={perTheme} /> : null}
          {side}
        </div>
      ) : (
        <div className="lx-stack">
          {has("today") ? <TodayByTheme perTheme={perTheme} /> : null}
          {side}
        </div>
      )}
    </div>
  );
}
