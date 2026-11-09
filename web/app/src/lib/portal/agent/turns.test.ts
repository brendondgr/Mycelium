import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { availabilityFrom, modelLine } from "./availability";
import { backoff, followThread, parseStream, SseParser } from "./stream";
import {
  apply,
  applyAll,
  currentActivity,
  emptyView,
  foldSummary,
  splitCitations,
  turnStatus,
  viewFromEvents,
} from "./turns";
import type { AgentEvent, StreamMessage } from "./types";

/*
 * The fixtures are a real turn recorded from the backend: `tools/agent`'s own
 * scripted three-call turn (thinking, three calls, an answer) read back
 * through `stream/?once=1` and `events/` in the activity view.
 */
const here = path.dirname(new URL(import.meta.url).pathname);
const SSE = readFileSync(path.join(here, "__fixtures__/three-step-turn.sse.txt"), "utf8");
const EVENTS = JSON.parse(
  readFileSync(path.join(here, "__fixtures__/three-step-turn.events.json"), "utf8"),
) as { events: AgentEvent[]; state: string };

const messages = parseStream(SSE);
const whole = applyAll(emptyView(), messages);

describe("the recorded three-step turn", () => {
  it("parses every stored event", () => {
    expect(messages.map((m) => m.id)).toEqual([1, 2, 5, 7, 8, 9, 10, 11, 12, 14, 16, 17]);
  });

  it("becomes one turn: question, three labelled steps, the answer", () => {
    expect(whole.turns).toHaveLength(1);
    const [turn] = whole.turns;
    expect(turn.user?.text).toBe("what's new?");
    expect(turn.steps.map((s) => [s.label, s.state])).toEqual([
      ["Looking at your profile", "ok"],
      ["Searching the corpus for “cell segmentation”", "ok"],
      ["Looking at saved items", "ok"],
    ]);
    expect(turn.answer?.text).toBe("Here is what I found.");
    expect(turn.answer?.final).toBe(true);
    expect(turn.thinking).toBe(false);
    expect(whole.state).toBe("idle");
    expect(whole.model?.location).toBe("local");
    expect(whole.lastSeq).toBe(17);
    expect(turnStatus(turn, true, whole.state)).toBe("done");
    expect(foldSummary(turn.steps)).toBe("Looked at 3 things");
  });

  it("is the same whether delivered in two halves across a reconnect", () => {
    const half = applyAll(emptyView(), messages.slice(0, 6));
    // the resumed stream replays from Last-Event-ID; the server may resend
    // the boundary event, which is dropped
    const resumed = messages.filter((m) => (m.id ?? 0) >= half.lastSeq);
    expect(applyAll(half, resumed)).toEqual(whole);
  });

  it("is the same with every event duplicated", () => {
    const doubled = messages.flatMap((m) => [m, m]);
    expect(applyAll(emptyView(), doubled)).toEqual(whole);
  });

  it("is the same when the whole stream is replayed after it was applied", () => {
    expect(applyAll(whole, messages)).toBe(whole);
  });

  it("is the same read from events/ as from the stream", () => {
    expect(viewFromEvents(EVENTS.events, EVENTS.state)).toEqual(whole);
  });

  it("never holds reasoning text", () => {
    const thinking = messages.find(
      (m) => m.type === "activity" && m.payload?.state === "thinking",
    );
    expect(thinking?.payload).toEqual({ state: "thinking" });
    expect(JSON.stringify(whole)).not.toMatch(/reason/i);
  });

  it("shows what Mylo is doing at each point of the turn", () => {
    let view = emptyView();
    const seen: string[] = [];
    for (const m of messages) {
      view = apply(view, m);
      const turn = view.turns[view.turns.length - 1];
      if (turn && view.state === "running") seen.push(currentActivity(turn));
    }
    expect(seen).toEqual([
      "Thinking",
      "Thinking",
      "Looking at your profile",
      "Searching the corpus for “cell segmentation”",
      "Looking at saved items",
      "Looking at saved items",
      "Looking at saved items",
      "Putting it together",
      "Putting it together",
    ]);
  });
});

describe("live messages", () => {
  const user: StreamMessage = { id: 1, type: "user", payload: { text: "hi" } };
  const running: StreamMessage = { id: 2, type: "state", payload: { state: "running" } };

  it("streams text into a draft that the stored answer replaces", () => {
    let view = applyAll(emptyView(), [user, running]);
    view = apply(view, { type: "delta", kind: "text", text: "Hel" });
    view = apply(view, { type: "delta", kind: "text", text: "lo" });
    expect(view.turns[0].draft).toBe("Hello");
    expect(currentActivity(view.turns[0])).toBe("Writing");
    view = apply(view, { id: 3, type: "assistant", payload: { text: "Hello.", final: true } });
    expect(view.turns[0].draft).toBe("");
    expect(view.turns[0].answer?.text).toBe("Hello.");
  });

  it("ignores thinking deltas: they never reach the view", () => {
    const view = applyAll(emptyView(), [user, running]);
    expect(apply(view, { type: "delta", kind: "thinking", text: "secret" })).toBe(view);
  });

  it("keeps a question for the dock and records the answer", () => {
    let view = applyAll(emptyView(), [
      user,
      running,
      { id: 3, type: "activity", payload: { state: "running", call_id: "q", name: "ask_user", label: "Asking you" } },
      { id: 4, type: "question", payload: { call_id: "q", question: "Which lab?", options: ["A", "B"] } },
      { id: 5, type: "state", payload: { state: "waiting" } },
    ]);
    expect(view.turns[0].steps).toEqual([]);
    expect(turnStatus(view.turns[0], true, view.state)).toBe("waiting");
    view = apply(view, { id: 6, type: "answer", payload: { call_id: "q", text: "A" } });
    expect(view.turns[0].question?.answer).toBe("A");
  });

  it("keeps an error in plain words and closes open steps", () => {
    const view = applyAll(emptyView(), [
      user,
      running,
      { id: 3, type: "activity", payload: { state: "running", call_id: "a", name: "x", label: "Reading" } },
      { id: 4, type: "error", payload: { code: "turn_failed", detail: "Boom.", fix: "Send the message again." } },
      { id: 5, type: "state", payload: { state: "error" } },
    ]);
    const [turn] = view.turns;
    expect(turn.errors[0].fix).toBe("Send the message again.");
    expect(turn.steps[0].state).toBe("failed");
    expect(turnStatus(turn, true, view.state)).toBe("failed");
  });

  it("marks a stopped turn", () => {
    const view = applyAll(emptyView(), [
      user,
      running,
      { id: 3, type: "assistant", payload: { text: "Part", partial: true } },
      { id: 4, type: "note", payload: { text: "Stopped." } },
      { id: 5, type: "state", payload: { state: "idle" } },
    ]);
    expect(view.turns[0].stopped).toBe(true);
    expect(view.turns[0].answer?.partial).toBe(true);
  });
});

describe("the stream parser", () => {
  it("gives the same messages however the bytes are chunked", () => {
    for (const size of [1, 7, 64, 500]) {
      const parser = new SseParser();
      const out: StreamMessage[] = [];
      for (let i = 0; i < SSE.length; i += size) out.push(...parser.push(SSE.slice(i, i + size)));
      expect(out).toEqual(messages);
    }
  });

  it("skips heartbeats", () => {
    expect(parseStream(": heartbeat\n\n")).toEqual([]);
  });

  it("caps the backoff", () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(backoff)).toEqual([1000, 2000, 4000, 8000, 15000, 15000, 15000]);
  });
});

describe("followThread", () => {
  function body(text: string) {
    return new Response(new Blob([text]).stream(), { status: 200 });
  }

  it("resumes from the last applied event after a drop, with no repeats", async () => {
    const blocks = SSE.split("\n\n").filter(Boolean).map((b) => `${b}\n\n`);
    const first = blocks.slice(0, 5).join("");
    const requests: { url: string; lastId: string | null }[] = [];
    const fetchImpl = (async (url: string, init: RequestInit) => {
      const headers = (init.headers ?? {}) as Record<string, string>;
      requests.push({ url, lastId: headers["Last-Event-ID"] ?? null });
      if (requests.length === 1) return body(first);
      // the server resends from Last-Event-ID; include the boundary again
      return body(blocks.slice(4).join(""));
    }) as unknown as typeof fetch;

    let view = emptyView("running");
    const states: string[] = [];
    await new Promise<void>((resolve) => {
      followThread({
        url: "/api/tools/agent/threads/t/stream/",
        lastSeq: () => view.lastSeq,
        onMessage: (m) => {
          view = apply(view, m);
        },
        onState: (s) => states.push(s),
        stillRunning: () => view.state === "running",
        onEnd: resolve,
        fetchImpl,
        sleep: async () => {},
      });
    });
    expect(requests).toHaveLength(2);
    expect(requests[0].lastId).toBeNull();
    expect(requests[1].lastId).toBe("8");
    expect(requests[1].url).toContain("after=8");
    expect(requests[0].url).toContain("until_idle=1");
    expect(states).toEqual(["live", "reconnecting", "live", "idle"]);
    expect(view).toEqual(whole);
  });

  it("stops on a refusal instead of retrying it", async () => {
    let calls = 0;
    const fetchImpl = (async () => {
      calls += 1;
      return new Response("{}", { status: 403 });
    }) as unknown as typeof fetch;
    await new Promise<void>((resolve) => {
      followThread({
        url: "/x/",
        lastSeq: () => 0,
        onMessage: () => {},
        onState: () => {},
        stillRunning: () => true,
        onEnd: resolve,
        fetchImpl,
        sleep: async () => {},
      });
    });
    expect(calls).toBe(1);
  });
});

describe("availability", () => {
  const model = { name: "m", label: "Qwen", location: "local" };

  it("is allowed when the gate allows and a model is set", () => {
    expect(
      availabilityFrom({ ok: true, functions: [{ name: "a", group: "g", summary: "", allowed: true }] }, { model }),
    ).toEqual({ state: "allowed", model });
  });

  it("says the gate's own refusal", () => {
    const out = availabilityFrom(
      {
        ok: true,
        functions: [
          { name: "*", group: "*", summary: "", allowed: false, code: "chat_off", detail: "Off.", fix: "Turn it on." },
        ],
      },
      { model },
    );
    expect(out).toEqual({ state: "denied", refusal: { code: "chat_off", detail: "Off.", fix: "Turn it on." } });
  });

  it("explains an unverified email and a missing model", () => {
    const unverified = availabilityFrom(
      { ok: false, status: 403, refusal: { code: "unverified", detail: "Verify.", fix: "" } },
      undefined,
    );
    expect(unverified.state === "denied" && unverified.refusal.fix).toBeTruthy();
    expect(
      availabilityFrom({ ok: true, functions: [] }, { model: null, code: "no_model", detail: "None.", fix: "Set it." }),
    ).toEqual({ state: "denied", refusal: { code: "no_model", detail: "None.", fix: "Set it." } });
  });

  it("draws nothing when the agent is not installed", () => {
    expect(availabilityFrom({ ok: false, status: 404, refusal: { code: "not_found", detail: "", fix: "" } }, undefined)).toEqual({
      state: "absent",
    });
  });

  it("names where the model runs", () => {
    expect(modelLine(model)).toBe("Qwen · runs on this machine");
  });
});

describe("citations", () => {
  it("splits #n out of the answer", () => {
    expect(splitCitations("Yes #1, and #12.")).toEqual([
      { text: "Yes " },
      { cite: 1 },
      { text: ", and " },
      { cite: 12 },
      { text: "." },
    ]);
  });
});
