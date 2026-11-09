/**
 * The turn model the panel draws, built from the activity view.
 *
 * A turn starts at the person's message. It holds the steps Mylo took (one
 * per call, each with the server's label and a tick or a cross), the answer,
 * a question Mylo asked, and any error. There is no field for reasoning: the
 * activity view sends a bare `{state: "thinking"}` marker, which only sets
 * `thinking` while Mylo has not yet started its next step.
 *
 * `apply` is idempotent for stored events — anything at or below `lastSeq` is
 * dropped — so the same turn comes out whether the events arrive whole, in
 * two halves across a reconnect, or with repeats. Transient messages (text
 * deltas) carry no seq; they only fill `draft`, which the stored `assistant`
 * event replaces.
 */

import type { AgentEvent, AgentModel, StreamMessage, ThreadState } from "./types";

/** The function behind Mylo's questions: drawn by the question dock, not as a step. */
export const ASK_USER = "ask_user";

export type StepState = "running" | "ok" | "failed";

export type Step = { callId: string; label: string; name: string; state: StepState };

export type TurnQuestion = {
  callId: string;
  question: string;
  options: string[];
  /** The person's answer, once given. */
  answer: string | null;
};

export type TurnError = { code: string; detail: string; fix: string };

export type Turn = {
  /** The seq of the event that opened it (0 before any message). */
  key: number;
  user: { text: string; mentions: string[]; ts: string | null } | null;
  steps: Step[];
  /** Mylo is between steps and has said nothing yet. Never carries text. */
  thinking: boolean;
  answer: {
    text: string;
    final: boolean;
    partial: boolean;
    removed: number[];
    model: AgentModel | null;
  } | null;
  /** Text streaming in before the stored answer lands. */
  draft: string;
  question: TurnQuestion | null;
  errors: TurnError[];
  notes: string[];
  stopped: boolean;
  startedAt: string | null;
  endedAt: string | null;
};

export type ThreadView = {
  turns: Turn[];
  lastSeq: number;
  state: ThreadState;
  model: AgentModel | null;
};

export function emptyView(state: ThreadState = "idle"): ThreadView {
  return { turns: [], lastSeq: 0, state, model: null };
}

function newTurn(key: number, ts: string | null): Turn {
  return {
    key,
    user: null,
    steps: [],
    thinking: false,
    answer: null,
    draft: "",
    question: null,
    errors: [],
    notes: [],
    stopped: false,
    startedAt: ts,
    endedAt: null,
  };
}

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** A stored event from `events/` as a stream message. */
export function fromEvent(event: AgentEvent): StreamMessage {
  return { id: event.seq, type: event.type, ts: event.ts, payload: event.payload };
}

/**
 * Apply one message. Returns a new view (the input is never changed), or the
 * same view when the message changes nothing.
 */
export function apply(view: ThreadView, message: StreamMessage): ThreadView {
  const seq = typeof message.id === "number" ? message.id : null;
  if (seq !== null && seq <= view.lastSeq) return view;
  const next: ThreadView = {
    ...view,
    turns: view.turns.slice(),
    lastSeq: seq ?? view.lastSeq,
  };
  const payload = (message.payload ?? {}) as Record<string, unknown>;
  const ts = message.ts ?? null;

  const current = (): Turn => {
    let turn = next.turns[next.turns.length - 1];
    if (!turn) {
      turn = newTurn(0, ts);
      next.turns.push(turn);
      return turn;
    }
    if (turn === view.turns[view.turns.length - 1]) {
      // copy on write: the previous view keeps its own turn
      turn = { ...turn, steps: turn.steps.slice(), errors: turn.errors.slice(), notes: turn.notes.slice() };
      next.turns[next.turns.length - 1] = turn;
    }
    return turn;
  };

  switch (message.type) {
    case "user": {
      const turn = newTurn(seq ?? 0, ts);
      turn.user = {
        text: str(payload.text),
        mentions: Array.isArray(payload.mentions) ? payload.mentions.map(String) : [],
        ts,
      };
      next.turns.push(turn);
      return next;
    }
    case "activity": {
      const turn = current();
      const state = str(payload.state);
      if (state === "thinking") {
        turn.thinking = true;
        return next;
      }
      const callId = str(payload.call_id);
      const name = str(payload.name);
      turn.thinking = false;
      if (name === ASK_USER || !callId) return next;
      const step: Step = {
        callId,
        name,
        label: str(payload.label) || "Working",
        state: state === "ok" ? "ok" : state === "failed" ? "failed" : "running",
      };
      const at = turn.steps.findIndex((s) => s.callId === callId);
      if (at >= 0) {
        // a step never goes back to running once it has closed
        if (step.state === "running" && turn.steps[at].state !== "running") return next;
        turn.steps[at] = step;
      } else {
        turn.steps.push(step);
      }
      return next;
    }
    case "delta": {
      if (message.kind !== "text" || !message.text) return view;
      const turn = current();
      turn.draft += message.text;
      turn.thinking = false;
      return next;
    }
    case "assistant": {
      const turn = current();
      const text = str(payload.text);
      const model = (payload.model as AgentModel | undefined) ?? null;
      if (model) next.model = model;
      turn.thinking = false;
      turn.draft = "";
      if (text.trim() || payload.final) {
        turn.answer = {
          text,
          final: Boolean(payload.final),
          partial: Boolean(payload.partial),
          removed: Array.isArray(payload.removed) ? payload.removed.map(Number) : [],
          model,
        };
      }
      if (payload.final || payload.partial) turn.endedAt = ts;
      return next;
    }
    case "question": {
      const turn = current();
      turn.thinking = false;
      turn.question = {
        callId: str(payload.call_id),
        question: str(payload.question),
        options: Array.isArray(payload.options) ? payload.options.map(String) : [],
        answer: null,
      };
      return next;
    }
    case "answer": {
      const turn = current();
      if (turn.question && turn.question.callId === str(payload.call_id)) {
        turn.question = { ...turn.question, answer: str(payload.text) };
      }
      return next;
    }
    case "error": {
      const turn = current();
      turn.thinking = false;
      turn.errors.push({
        code: str(payload.code),
        detail: str(payload.detail) || "Something went wrong.",
        fix: str(payload.fix),
      });
      turn.endedAt = ts;
      return next;
    }
    case "note": {
      const text = str(payload.text);
      if (!text) return seq !== null ? next : view;
      const turn = current();
      if (text === "Stopped.") {
        turn.stopped = true;
        turn.thinking = false;
        turn.endedAt = ts;
      } else {
        turn.notes.push(text);
      }
      return next;
    }
    case "state": {
      next.state = str(payload.state) || next.state;
      if (next.state !== "running" && next.turns.length) {
        const turn = current();
        turn.thinking = false;
        turn.draft = "";
        // a run that ended mid-step left that step open: it did not finish
        if (next.state !== "waiting") {
          turn.steps = turn.steps.map((s) =>
            s.state === "running" ? { ...s, state: "failed" } : s,
          );
        }
      }
      return next;
    }
    default:
      // heartbeats, the context meter, todos and anything new: nothing to draw
      return seq !== null ? next : view;
  }
}

export function applyAll(view: ThreadView, messages: StreamMessage[]): ThreadView {
  return messages.reduce(apply, view);
}

/** Build a view from `events/` in one go. */
export function viewFromEvents(events: AgentEvent[], state: ThreadState): ThreadView {
  const view = applyAll(emptyView(), events.map(fromEvent));
  return { ...view, state };
}

export type TurnStatus = "working" | "waiting" | "failed" | "stopped" | "done";

/** What a turn is doing now. Only the last turn can still be working. */
export function turnStatus(turn: Turn, isLast: boolean, threadState: ThreadState): TurnStatus {
  if (turn.errors.length) return "failed";
  if (turn.stopped) return "stopped";
  if (isLast && threadState === "waiting" && turn.question && !turn.question.answer) {
    return "waiting";
  }
  if (isLast && threadState === "running") return "working";
  return "done";
}

/** The fold's header once a turn has ended: "Looked at 3 things". */
export function foldSummary(steps: Step[]): string {
  const n = steps.length;
  if (!n) return "";
  const failed = steps.filter((s) => s.state === "failed").length;
  const head = n === 1 ? "Looked at 1 thing" : `Looked at ${n} things`;
  return failed ? `${head} · ${failed} didn’t work` : head;
}

/**
 * The fold's header while Mylo works: the step running now, or thinking.
 * Between two steps the last step's label stays: Mylo thinks for a moment
 * after every step, and swapping the words each time reads as flicker.
 */
export function currentActivity(turn: Turn): string {
  const running = [...turn.steps].reverse().find((s) => s.state === "running");
  if (running) return running.label;
  if (turn.draft) return "Writing";
  const last = turn.steps[turn.steps.length - 1];
  return last ? last.label : "Thinking";
}

/** Split answer text into plain runs and `#n` citations. */
export type AnswerPart = { text: string } | { cite: number };

export function splitCitations(text: string): AnswerPart[] {
  const out: AnswerPart[] = [];
  const re = /#(\d+)\b/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) });
    out.push({ cite: Number(m[1]) });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}
