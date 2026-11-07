"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { usePortal } from "@/components/portal/portal-context";
import { statusDotColor, displayStatus } from "@/components/portal/project-status";
import { BestFor, DeadlinePill, MyloMark, ThemeTag, daysUntil, type ThemeRef } from "@/components/portal/feed/parts";
import { LinesSkeleton } from "@/components/portal/skeleton";
import { useAnswerSuggestion, useSuggestions } from "@/lib/portal/ambient/hooks";
import { SECTION_ROUTES, routeWithScope, type SectionKey } from "@/lib/portal/routes";
import { scopeKey } from "@/lib/portal/workspace";
import type {
  ConferenceOpportunity,
  FellowshipOpportunity,
  GrantOpportunity,
  OpportunityBase,
  RecommendedMember,
  Suggestion,
} from "@/lib/portal/types";

/**
 * The overview's shared parts (the split layout chosen in `/labs`): a main
 * column with Mylo's written report and today's new items grouped by theme,
 * and a side column of closing-soon deadlines, who each item is for, Mylo's
 * questions, project pulse and what Mylo found. The personal and the lab
 * overview both compose these, so the two read the same.
 *
 * Every item links into its feed with `?item=`, which opens it there.
 */

export type OverviewKind = "paper" | "grant" | "fellowship" | "conference";

export type OverviewItem = {
  kind: OverviewKind;
  id: string;
  title: string;
  reason: string;
  byMylo: boolean;
  theme: ThemeRef | null;
  deadline: string;
  isNew: boolean;
  members?: RecommendedMember[];
};

const KIND_LABEL: Record<OverviewKind, string> = {
  paper: "Paper",
  grant: "Grant",
  fellowship: "Fellowship",
  conference: "Conference",
};

const KIND_SECTION: Record<OverviewKind, SectionKey> = {
  paper: "papers",
  grant: "opportunities",
  fellowship: "fellowships",
  conference: "conferences",
};

/** Flatten the four feeds into one list the overview panels can share. */
export function overviewItems({
  papers = [],
  grants = [],
  fellowships = [],
  conferences = [],
  recommendedFor,
}: {
  papers?: Suggestion[];
  grants?: GrantOpportunity[];
  fellowships?: FellowshipOpportunity[];
  conferences?: ConferenceOpportunity[];
  recommendedFor?: Record<string, RecommendedMember[]>;
}): OverviewItem[] {
  const opp = (kind: OverviewKind) => (o: OpportunityBase): OverviewItem => ({
    kind,
    id: o.content_id,
    title: o.title,
    reason: o.beats[0] || o.reason,
    byMylo: o.origin === "llm",
    theme: o.cluster ?? null,
    deadline: o.deadline_date,
    isNew: o.is_new,
    members: recommendedFor?.[o.content_id],
  });
  return [
    ...papers.map(
      (p): OverviewItem => ({
        kind: "paper",
        id: p.content_id,
        title: p.headline || p.title,
        reason: p.beats[0] || p.reason,
        byMylo: p.origin === "llm",
        theme: p.cluster,
        deadline: "",
        isNew: p.is_new,
        members: recommendedFor?.[p.content_id],
      }),
    ),
    ...grants.map(opp("grant")),
    ...fellowships.map(opp("fellowship")),
    ...conferences.map(opp("conference")),
  ];
}

function useItemHref() {
  const { scope } = usePortal();
  const key = scopeKey(scope);
  return React.useCallback(
    (item: OverviewItem) => {
      const base = routeWithScope(SECTION_ROUTES[KIND_SECTION[item.kind]], key);
      return `${base}${base.includes("?") ? "&" : "?"}item=${encodeURIComponent(item.id)}`;
    },
    [key],
  );
}

function useSectionHref() {
  const { scope } = usePortal();
  const key = scopeKey(scope);
  return (section: SectionKey) => routeWithScope(SECTION_ROUTES[section], key);
}

/** Only on the client: the time of day and the date are the reader's, not the server's. */
function useNow(): Date | null {
  const mounted = React.useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  return React.useMemo(() => (mounted ? new Date() : null), [mounted]);
}

export function OverviewHead({ subject, action }: { subject: string; action?: React.ReactNode }) {
  const { user } = usePortal();
  const now = useNow();
  const first = (user.name || user.username).split(" ")[0];
  const hour = now?.getHours() ?? 9;
  const greeting = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  const date = now?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  return (
    <header className="ws-page-head">
      <div className="min-w-0">
        <p className="ws-kicker">{date ?? " "}</p>
        <h1 className="ws-h ws-page-title">{now ? `Good ${greeting}, ${first}.` : `Welcome back, ${first}.`}</h1>
        <p className="ws-lede">What changed in {subject} field overnight, and who it is for.</p>
      </div>
      {action ? <div className="ws-page-tools">{action}</div> : null}
    </header>
  );
}

export function Panel({
  title,
  action,
  href,
  children,
}: {
  title: string;
  action?: string;
  href?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="ws-panel-box ws-rise" aria-label={title}>
      <div className="ws-panel-head">
        <h2 className="ws-h ws-panel-title">{title}</h2>
        {action && href ? (
          <Link className="ws-link" href={href}>
            {action} <ArrowRight size={13} aria-hidden="true" />
          </Link>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function Reason({ item }: { item: OverviewItem }) {
  if (!item.reason) return null;
  return (
    <p className="ws-compact-why">
      {item.byMylo ? <MyloMark size={16} /> : null}
      <span className="ws-clamp">{item.reason}</span>
    </p>
  );
}

/** Every kind of new item, under the theme it was matched to. */
export function TodayByTheme({
  items,
  isLoading,
  perTheme = 3,
}: {
  items: OverviewItem[];
  isLoading: boolean;
  perTheme?: number;
}) {
  const href = useItemHref();
  const section = useSectionHref();
  const fresh = items.filter((i) => i.isNew);
  const groups = new Map<string, { theme: ThemeRef | null; items: OverviewItem[] }>();
  for (const i of fresh) {
    const key = i.theme?.id ?? "__none";
    if (!groups.has(key)) groups.set(key, { theme: i.theme, items: [] });
    groups.get(key)!.items.push(i);
  }
  return (
    <Panel title="New this week, by theme" action="All papers" href={section("papers")}>
      {isLoading ? (
        <LinesSkeleton rows={4} />
      ) : fresh.length === 0 ? (
        <p className="ws-meta-text">
          Nothing new entered your lists this week. Mylo re-ranks everything each night; new matches land here.
        </p>
      ) : (
        <div className="ws-theme-groups">
          {[...groups.values()].map((g) => (
            <div key={g.theme?.id ?? "none"} className="ws-theme-group">
              <div className="ws-theme-group-head">
                {g.theme ? <ThemeTag theme={g.theme} /> : <span className="ws-kind">Other matches</span>}
                <span className="ws-meta-text">{g.items.length} new</span>
              </div>
              <ul className="ws-compact-list">
                {g.items.slice(0, perTheme).map((i) => (
                  <li key={`${i.kind}-${i.id}`}>
                    <span className="ws-row-kind">
                      <span className="ws-kind-chip">{KIND_LABEL[i.kind]}</span>
                      {i.deadline ? <DeadlinePill date={i.deadline} /> : null}
                    </span>
                    <Link className="ws-compact-title" href={href(i)}>
                      {i.title}
                    </Link>
                    <Reason item={i} />
                    <BestFor members={i.members} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

/** Grants, fellowships and conferences closing within 30 days, soonest first. */
export function ClosingSoon({ items, isLoading }: { items: OverviewItem[]; isLoading: boolean }) {
  const href = useItemHref();
  const section = useSectionHref();
  const soon = items
    .map((i) => ({ i, d: daysUntil(i.deadline) }))
    .filter((x): x is { i: OverviewItem; d: number } => x.d !== null && x.d >= 0 && x.d <= 30)
    .sort((a, b) => a.d - b.d)
    .slice(0, 6);
  return (
    <Panel title="Closing soon" action="Saves" href={section("saves")}>
      {isLoading ? (
        <LinesSkeleton rows={2} />
      ) : soon.length === 0 ? (
        <p className="ws-meta-text">Nothing matched closes in the next 30 days.</p>
      ) : (
        <ul className="ws-compact-list">
          {soon.map(({ i }) => (
            <li key={`${i.kind}-${i.id}`}>
              <span className="ws-row-kind">
                <DeadlinePill date={i.deadline} />
                <span className="ws-meta-text">{KIND_LABEL[i.kind]}</span>
              </span>
              <Link className="ws-compact-title" href={href(i)}>
                {i.title}
              </Link>
              <BestFor members={i.members} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** Per person: how much Mylo set aside for them, and the one to read first. */
export function ForEachPerson({ items, isLoading }: { items: OverviewItem[]; isLoading: boolean }) {
  const href = useItemHref();
  const section = useSectionHref();
  const people = new Map<string, { member: RecommendedMember; items: OverviewItem[] }>();
  for (const i of items)
    for (const m of i.members ?? []) {
      if (!people.has(m.username)) people.set(m.username, { member: m, items: [] });
      people.get(m.username)!.items.push(i);
    }
  const list = [...people.values()].sort((a, b) => b.items.length - a.items.length).slice(0, 6);
  return (
    <Panel title="For each person" action="Members" href={section("members")}>
      {isLoading ? (
        <LinesSkeleton rows={3} />
      ) : list.length === 0 ? (
        <p className="ws-meta-text">Mylo hasn&apos;t matched today&apos;s items to anyone in the lab yet.</p>
      ) : (
        <ul className="ws-person-list">
          {list.map(({ member, items: theirs }) => {
            const first = theirs.find((i) => i.isNew) ?? theirs[0];
            return (
              <li key={member.username}>
                <span className="ws-avatar-sm ws-avatar-md" aria-hidden="true">
                  {member.initials}
                </span>
                <span className="ws-person-body">
                  <span className="ws-person">
                    {member.name} <span className="ws-meta-text">· {theirs.length} for them</span>
                  </span>
                  <Link className="ws-person-first" href={href(first)}>
                    Start with: {first.title}
                  </Link>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

/** Mylo's open questions, answerable right here. */
export function MyloAsks() {
  const section = useSectionHref();
  const { data, isLoading } = useSuggestions();
  const answer = useAnswerSuggestion();
  const [done, setDone] = React.useState<Record<number, string>>({});
  const open = (data?.suggestions ?? []).filter((s) => s.state === "asked" || s.state === "pending").slice(0, 3);
  if (!isLoading && open.length === 0 && Object.keys(done).length === 0) return null;
  return (
    <Panel title="Mylo is asking" action="Mylo & you" href={section("mylo")}>
      {isLoading ? (
        <LinesSkeleton rows={2} />
      ) : (
        <ul className="ws-asks">
          {open.map((s) => (
            <li key={s.id}>
              <p className="ws-ask-q">
                <MyloMark size={18} />
                <span>{s.question}</span>
              </p>
              {s.explanation ? <p className="ws-meta-text">{s.explanation}</p> : null}
              {done[s.id] ? (
                <p className="ws-ask-done" role="status">
                  Noted: {done[s.id]}.
                </p>
              ) : (
                <div className="ws-ask-actions">
                  {s.choices.map((c, n) => (
                    <button
                      key={c.key}
                      type="button"
                      disabled={answer.isPending}
                      className={`ws-btn ${n === 0 ? "ws-btn-solid" : "ws-btn-line"} ws-btn-sm`}
                      onClick={() =>
                        answer.mutate(
                          { id: s.id, choice: c.key },
                          { onSuccess: () => setDone((prev) => ({ ...prev, [s.id]: c.label })) },
                        )
                      }
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** The workspace's projects, with their state, most recently changed first. */
export function ProjectPulse() {
  const { projects, projectsLoading, openProject } = usePortal();
  const section = useSectionHref();
  const list = [...projects]
    .filter((p) => !p.is_archived)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 4);
  return (
    <Panel title="Project pulse" action="Projects" href={section("projects")}>
      {projectsLoading ? (
        <LinesSkeleton rows={2} />
      ) : list.length === 0 ? (
        <p className="ws-meta-text">No projects yet. A project gives Mylo a focus to match against.</p>
      ) : (
        <ul className="ws-compact-list">
          {list.map((p) => (
            <li key={p.id} className="ws-project">
              <button type="button" className="ws-compact-title" onClick={() => openProject(p.id)}>
                {p.name}
              </button>
              <span className="ws-pill">
                <span
                  aria-hidden="true"
                  className="mr-1.5 inline-block h-[7px] w-[7px] rounded-full"
                  style={{ background: statusDotColor(p.status) }}
                />
                {displayStatus(p.status)}
              </span>
              {p.description ? <p className="ws-compact-why ws-clamp">{p.description}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/**
 * Mylo's written report, folded to a fixed height with a way to open it in
 * full — the page scrolls as one, so the report must not push everything
 * else a screen away, and it must not become a scroll area of its own.
 */
export function FoldedReport({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [tall, setTall] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const id = React.useId();

  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const check = () => setTall(el.scrollHeight > 640);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="ws-fold" data-open={open || !tall || undefined}>
      <div ref={ref} id={id} className="ws-fold-body">
        {children}
      </div>
      {tall ? (
        <button type="button" className="ws-fold-btn ws-link" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
          {open ? "Fold the report" : "Read the whole report"}
        </button>
      ) : null}
    </div>
  );
}
