"use client";

import { useAppHref, useAppRouter, useDemo } from "@/components/demo/demo-context";
import Link from "next/link";
import * as React from "react";
import { History, Pin, SquarePen, X } from "lucide-react";

import { modelLine } from "@/lib/portal/agent/availability";
import { turnStatus } from "@/lib/portal/agent/turns";
import type {
  AgentAnchor,
  AgentModel,
  AgentReference,
  AgentRefusal,
  AgentThread,
  ChatAvailability,
} from "@/lib/portal/agent/types";
import { useThreadRuntime } from "@/lib/portal/agent/use-thread";
import type { NewThread } from "@/lib/portal/agent/client";
import { useAgentThread, useUpdateAgentThread } from "@/lib/portal/hooks";
import { SECTION_ROUTES } from "@/lib/portal/routes";

import { Composer } from "./composer";
import type { AskMyloRequest } from "./events";
import { HistoryList } from "./history";
import { MyloHead } from "./mylo-head";
import { openRef, splitItemTitle } from "./open-ref";
import { QuestionDock } from "./question-dock";
import { Turn } from "./turn";

/** What the panel is showing: one conversation, stored or not yet. */
export type Session = {
  /** Changes whenever the panel switches conversation (keys the view). */
  key: number;
  threadId: string | null;
  draft: NewThread;
  /** The thing an anchored conversation is about, as the button named it. */
  about: AskMyloRequest | null;
  /** Still looking for a conversation already open about `about`. */
  resolving?: boolean;
};

export type PanelView = "chat" | "history";

/**
 * The side panel. Structure after the Claude Code side panel: a header with
 * the title, history, new chat, pin and close; the conversation; the composer
 * with one line naming where the model runs. At 980 px and wider it lies over
 * the reading pane and the page stays usable; below that it is a full-screen
 * sheet with focus held inside, like the item drawer.
 */
export function ChatPanel({
  open,
  wide,
  session,
  view,
  availability,
  onClose,
  onNewChat,
  onShowHistory,
  onPick,
  onCreated,
  panelRef,
  inputRef,
}: {
  open: boolean;
  wide: boolean;
  session: Session;
  view: PanelView;
  availability: ChatAvailability;
  onClose: () => void;
  onNewChat: () => void;
  onShowHistory: (show: boolean) => void;
  onPick: (thread: AgentThread) => void;
  onCreated: (thread: AgentThread) => void;
  panelRef: React.RefObject<HTMLElement | null>;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  const thread = useAgentThread(session.threadId);
  const update = useUpdateAgentThread();
  const allowed = availability.state === "allowed";
  const meta = thread.data;
  const anchorRef = meta?.anchor ? meta.references.find((r) => r.n === 1) : undefined;
  const aboutTitle = anchorRef
    ? splitItemTitle(anchorRef.title).title
    : session.about?.title ?? "";
  const aboutAnchor = meta?.anchor ?? session.about?.anchor ?? null;
  const title = meta?.title || (aboutTitle ? `About ${aboutTitle}` : "New chat");

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (view === "history") onShowHistory(false);
      else onClose();
      return;
    }
    if (event.key === "Tab" && !wide) trapFocus(event, panelRef.current);
  };

  return (
    <div className="ws-mylo-layer" data-open={open || undefined} data-wide={wide || undefined}>
      {!wide ? (
        <button
          type="button"
          className="ws-scrim"
          aria-label="Close Mylo"
          tabIndex={-1}
          onClick={onClose}
        />
      ) : null}
      <aside
        ref={panelRef}
        className="ws-mylo-panel"
        aria-label="Mylo"
        role={wide ? "complementary" : "dialog"}
        aria-modal={wide ? undefined : true}
        aria-hidden={!open}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        inert={!open}
      >
        <header className="ws-mylo-header">
          <MyloHead size={30} />
          <div className="ws-mylo-titles">
            <TitleEditor
              key={meta?.id ?? "draft"}
              title={view === "history" ? "Conversations" : title}
              editable={Boolean(meta) && view === "chat"}
              onRename={(next) => meta && update.mutate({ id: meta.id, title: next })}
            />
            {view === "chat" && aboutAnchor && aboutTitle ? (
              <AboutLine
                anchor={aboutAnchor}
                title={aboutTitle}
                rawTitle={anchorRef?.title ?? aboutTitle}
                href={session.about?.href}
                onOpened={wide ? undefined : onClose}
              />
            ) : null}
          </div>
          <div className="ws-mylo-tools">
            <button
              type="button"
              className="ws-icon-btn"
              aria-label="History"
              title="History"
              aria-pressed={view === "history"}
              onClick={() => onShowHistory(view !== "history")}
              disabled={!allowed}
            >
              <History size={16} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="ws-icon-btn"
              aria-label="New chat"
              title="New chat"
              onClick={onNewChat}
              disabled={!allowed}
            >
              <SquarePen size={16} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="ws-icon-btn"
              aria-label={meta?.pinned ? "Unpin this chat" : "Pin this chat"}
              title={meta?.pinned ? "Unpin" : "Pin"}
              aria-pressed={Boolean(meta?.pinned)}
              disabled={!meta || view !== "chat"}
              onClick={() => meta && update.mutate({ id: meta.id, pinned: !meta.pinned })}
            >
              <Pin size={16} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="ws-icon-btn"
              aria-label="Close Mylo"
              title="Close"
              onClick={onClose}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        </header>

        {availability.state === "denied" ? (
          <NotAllowed refusal={availability.refusal} />
        ) : availability.state === "loading" ? (
          <Skeleton />
        ) : view === "history" ? (
          <HistoryList
            currentId={session.threadId}
            onPick={onPick}
            onDeleted={(id) => {
              if (id === session.threadId) onNewChat();
            }}
          />
        ) : (
          <Conversation
            key={session.key}
            session={session}
            model={availability.state === "allowed" ? availability.model : null}
            references={meta?.references ?? []}
            inputRef={inputRef}
            onCreated={onCreated}
            onCited={wide ? undefined : onClose}
            onNewChat={onNewChat}
          />
        )}
      </aside>
    </div>
  );
}

function Conversation({
  session,
  model,
  references,
  inputRef,
  onCreated,
  onCited,
  onNewChat,
}: {
  session: Session;
  model: AgentModel | null;
  references: AgentReference[];
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onCreated: (thread: AgentThread) => void;
  onCited?: () => void;
  onNewChat?: () => void;
}) {
  const router = useAppRouter();
  const runtime = useThreadRuntime({
    threadId: session.threadId,
    draft: session.draft,
    onCreated,
  });
  const { view } = runtime;
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const last = view.turns[view.turns.length - 1];
  const lastStatus = last ? turnStatus(last, true, view.state) : "done";
  const working = lastStatus === "working" || runtime.sending;
  const pendingQuestion =
    lastStatus === "waiting" && last?.question && !last.question.answer ? last.question : null;
  const shownModel = view.model ?? model;

  // The public demo allows a few questions (apps/demo/budget.py). Spend one
  // here once a send goes through; a demo refusal from the server spends them all.
  const demo = useDemo();
  const wasSending = React.useRef(false);
  React.useEffect(() => {
    if (wasSending.current && !runtime.sending && demo) {
      const refusal = runtime.sendError?.refusal;
      if (!refusal) demo.setBudget(Math.max(0, demo.questions_left - 1));
      else if (refusal.code.startsWith("demo_")) demo.setBudget(0, refusal);
    }
    wasSending.current = runtime.sending;
  }, [runtime.sending, runtime.sendError, demo]);
  const demoDone = demo !== null && demo.questions_left <= 0 && !pendingQuestion;

  // keep the newest turn in view as it grows
  const tail = `${view.lastSeq}:${last?.draft.length ?? 0}:${runtime.queued.length}`;
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [tail]);

  const cite = (ref: AgentReference) => {
    openRef(ref, (href) => router.push(href));
    onCited?.();
  };

  const loading = runtime.loading || session.resolving;

  return (
    <>
      {runtime.connection === "reconnecting" ? (
        <p className="ws-mylo-reconnect" role="status">
          Reconnecting…
        </p>
      ) : null}
      <div ref={scrollRef} className="ws-mylo-scroll" aria-busy={loading || undefined}>
        {loading ? (
          <Skeleton />
        ) : runtime.loadError ? (
          <div className="ws-mylo-error" role="alert">
            <div>
              <p>{runtime.loadError.detail}</p>
              {onNewChat ? (
                <button type="button" className="ws-mylo-link-btn" onClick={onNewChat}>
                  Start a new chat
                </button>
              ) : null}
            </div>
          </div>
        ) : view.turns.length === 0 && !runtime.sending && view.state !== "running" ? (
          demoDone ? (
            <NotAllowed refusal={demoRefusal(demo?.refusal)} />
          ) : (
            <Empty session={session} onPick={(q) => void runtime.send(q)} />
          )
        ) : (
          <ol className="ws-mylo-turns" aria-label="Conversation">
            {view.turns.map((turn, i) => {
              const isLast = i === view.turns.length - 1;
              return (
                <Turn
                  key={turn.key}
                  turn={turn}
                  isLast={isLast}
                  status={turnStatus(turn, isLast, view.state)}
                  references={references}
                  onCite={cite}
                  onRetry={(text) => void runtime.send(text)}
                />
              );
            })}
            {(runtime.sending || view.state === "running") && !view.turns.length ? (
              <li className="ws-mylo-turn">
                <div className="ws-mylo-msg" data-from="you">
                  <p className="ws-mylo-who">You</p>
                  <p className="ws-mylo-you ws-mylo-pending">Sending…</p>
                </div>
              </li>
            ) : null}
          </ol>
        )}
        {runtime.queued.length ? (
          <ul className="ws-mylo-queued" aria-label="Waiting to send">
            {runtime.queued.map((text, i) => (
              <li key={i}>
                <span className="ws-mylo-queued-tag">Queued</span> {text}
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {runtime.sendError && !runtime.sendError.refusal.code.startsWith("demo_") ? (
        <div className="ws-mylo-error ws-mylo-send-error" role="alert">
          <div>
            <p>{runtime.sendError.refusal.detail}</p>
            {runtime.sendError.refusal.fix ? (
              <p className="ws-mylo-fix">{runtime.sendError.refusal.fix}</p>
            ) : null}
            {runtime.sendError.text ? (
              <button
                type="button"
                className="ws-mylo-link-btn"
                onClick={() => void runtime.send(runtime.sendError!.text)}
              >
                Try again
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {pendingQuestion ? (
        <QuestionDock
          question={pendingQuestion}
          busy={runtime.sending}
          onAnswer={(text) => void runtime.answer(text)}
        />
      ) : null}

      {demoDone ? (
        <DemoAsked refusal={demoRefusal(demo?.refusal)} />
      ) : (
      <>
      {demo ? <DemoNote left={demo.questions_left} /> : null}
      <Composer
        inputRef={inputRef}
        threadId={session.threadId}
        working={working}
        waiting={Boolean(pendingQuestion)}
        placeholder={pendingQuestion ? "Answer Mylo…" : "Ask Mylo…"}
        footer={shownModel ? modelLine(shownModel) : null}
        onSend={(text, mentions) => void runtime.send(text, mentions)}
        onAnswer={(text) => void runtime.answer(text)}
        onStop={() => void runtime.cancel()}
      />
      </>
      )}
    </>
  );
}

/** The demo's refusal, or what to say once the visitor has had their question. */
function demoRefusal(refusal: AgentRefusal | null | undefined): AgentRefusal {
  return (
    refusal ?? {
      code: "demo_question_used",
      detail: "You've asked all your demo questions.",
      fix: "Sign up to keep asking Mylo, about your own lab.",
    }
  );
}

/** Above the demo's composer: how many questions are left, and that answers
 * can be slow — the demo shares one model with everyone using the instance. */
function DemoNote({ left }: { left: number }) {
  return (
    <p className="ws-mylo-demo-note">
      <strong>
        {left} demo question{left === 1 ? "" : "s"} left.
      </strong>{" "}
      Depending on the time of day, Mylo might be slower to respond.
    </p>
  );
}

/** In place of the composer once a demo visitor has used their questions. */
function DemoAsked({ refusal }: { refusal: AgentRefusal }) {
  return (
    <div className="ws-mylo-demo-asked" role="status">
      <p>
        <strong>{refusal.detail}</strong> {refusal.fix}
      </p>
      <a className="ws-mylo-chip" href="/signup">
        Sign up
      </a>
    </div>
  );
}

const STARTERS: Record<string, string[]> = {
  item: [
    "Why might this be worth my time?",
    "What does it ask for, in short?",
    "Who in my lab should see this?",
  ],
  project: [
    "What’s new for this project this week?",
    "What could help this project right now?",
    "Which open calls fit this project?",
  ],
  lab: [
    "What should the lab look at this week?",
    "Which open calls fit the lab?",
    "What are the lab’s projects working on?",
  ],
  department: [
    "Which department-level calls are open?",
    "Which labs could lead a new call?",
    "What has the department saved recently?",
  ],
  general: [
    "What’s new in my field this week?",
    "Which open calls fit my work?",
    "What have I saved recently?",
  ],
};

function Empty({ session, onPick }: { session: Session; onPick: (question: string) => void }) {
  const kind = session.about?.anchor.kind ?? (session.draft.scope && session.draft.scope !== "personal" ? session.draft.scope : "general");
  const starters = STARTERS[kind] ?? STARTERS.general;
  return (
    <div className="ws-mylo-empty">
      <MyloHead size={56} />
      <p className="ws-mylo-greet">
        {session.about
          ? `Ask me anything about “${session.about.title}”.`
          : "Hi. Ask me about your papers, calls, projects or lab."}
      </p>
      <ul className="ws-mylo-starters" aria-label="Starter questions">
        {starters.map((q) => (
          <li key={q}>
            <button type="button" className="ws-mylo-chip" onClick={() => onPick(q)}>
              {q}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="ws-mylo-skeleton" aria-hidden="true">
      <span className="ws-skel" style={{ width: "38%" }} />
      <span className="ws-skel" style={{ width: "82%" }} />
      <span className="ws-skel" style={{ width: "64%" }} />
      <span className="ws-skel" style={{ width: "74%" }} />
    </div>
  );
}

/** Where to change what refused the person, for the refusals that have a place. */
const WHERE: Record<string, { href: string; label: string }> = {
  chat_off: { href: SECTION_ROUTES.mylo, label: "Open Mylo & you" },
  not_entitled: { href: SECTION_ROUTES.account, label: "See your plan" },
  unverified: { href: SECTION_ROUTES.account, label: "Open Account" },
  // The public demo's question budget (apps/demo/budget.py).
  demo_question_used: { href: "/signup", label: "Sign up" },
  demo_closed_today: { href: "/signup", label: "Sign up" },
  demo_chat_off: { href: "/signup", label: "Sign up" },
};

function NotAllowed({ refusal }: { refusal: AgentRefusal }) {
  const appHref = useAppHref();
  const where = WHERE[refusal.code];
  return (
    <div className="ws-mylo-empty ws-mylo-denied" role="status">
      <MyloHead size={48} />
      <p className="ws-mylo-greet">{refusal.detail}</p>
      {refusal.fix ? <p className="ws-mylo-fix">{refusal.fix}</p> : null}
      {where ? (
        <Link className="ws-mylo-chip" href={appHref(where.href)}>
          {where.label}
        </Link>
      ) : null}
    </div>
  );
}

function AboutLine({
  anchor,
  title,
  rawTitle,
  href,
  onOpened,
}: {
  anchor: AgentAnchor;
  title: string;
  /** The agent's title, which names an item's kind ("[grant] …"). */
  rawTitle: string;
  /** Where the conversation was started from, when it was started here. */
  href?: string;
  onOpened?: () => void;
}) {
  const router = useAppRouter();
  return (
    <p className="ws-mylo-about">
      About:{" "}
      <button
        type="button"
        className="ws-mylo-about-link"
        title={title}
        onClick={() => {
          openRef({ kind: anchor.kind, key: anchor.key, title: rawTitle }, (to) => router.push(to), href);
          onOpened?.();
        }}
      >
        {title}
      </button>
    </p>
  );
}

function TitleEditor({
  title,
  editable,
  onRename,
}: {
  title: string;
  editable: boolean;
  onRename: (title: string) => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(title);
  if (editing) {
    return (
      <input
        className="ws-mylo-title-input"
        aria-label="Conversation title"
        value={value}
        autoFocus
        maxLength={200}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (value.trim() && value.trim() !== title) onRename(value.trim());
            setEditing(false);
          } else if (e.key === "Escape") {
            e.stopPropagation();
            setValue(title);
            setEditing(false);
          }
        }}
        onBlur={() => {
          if (value.trim() && value.trim() !== title) onRename(value.trim());
          setEditing(false);
        }}
      />
    );
  }
  return editable ? (
    <h2 className="ws-mylo-title">
      <button
        type="button"
        className="ws-mylo-title-btn"
        title="Rename"
        aria-label={`${title}, rename`}
        onClick={() => {
          setValue(title);
          setEditing(true);
        }}
      >
        {title}
      </button>
    </h2>
  ) : (
    <h2 className="ws-mylo-title">{title}</h2>
  );
}

/** Keep Tab inside the sheet while it covers the page. */
function trapFocus(event: React.KeyboardEvent, root: HTMLElement | null) {
  if (!root) return;
  const items = Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => el.offsetParent !== null);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
