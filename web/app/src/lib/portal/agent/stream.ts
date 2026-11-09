/**
 * The stream client for `threads/<id>/stream/` (server-sent events).
 *
 * A `fetch` reader rather than `EventSource`: the server names each event by
 * its type (`event: activity`, `event: assistant`, …), which `EventSource`
 * only delivers to a listener registered per name, and it cannot be told to
 * stop reconnecting once a turn has ended. With `fetch` the panel decides
 * when to resume, sends `Last-Event-ID` itself, and backs off on its own
 * schedule. The request is same-origin with the session cookie.
 *
 * The route is asked with `until_idle=1`, so it closes once the turn ends and
 * holds no server worker for an idle conversation. A close while the turn is
 * still running is a dropped connection: the client resumes from the last
 * stored event it applied, and the reducer drops anything it has already
 * seen, so a resume never repeats or skips a step.
 */

import type { StreamMessage } from "./types";

/** Incremental SSE parser: feed text chunks, get whole messages back. */
export class SseParser {
  private buffer = "";

  push(chunk: string): StreamMessage[] {
    this.buffer += chunk.replace(/\r\n?/g, "\n");
    const out: StreamMessage[] = [];
    let cut = this.buffer.indexOf("\n\n");
    while (cut >= 0) {
      const block = this.buffer.slice(0, cut);
      this.buffer = this.buffer.slice(cut + 2);
      const message = parseBlock(block);
      if (message) out.push(message);
      cut = this.buffer.indexOf("\n\n");
    }
    return out;
  }
}

/** One SSE block → its message, or null for a comment (the heartbeat). */
export function parseBlock(block: string): StreamMessage | null {
  let id: number | undefined;
  let event = "";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") {
      const n = Number(value);
      if (Number.isFinite(n)) id = n;
    } else if (field === "event") {
      event = value;
    } else if (field === "data") {
      data.push(value);
    }
  }
  if (!data.length) return null;
  let parsed: StreamMessage;
  try {
    parsed = JSON.parse(data.join("\n")) as StreamMessage;
  } catch {
    return null;
  }
  if (!parsed.type && event) parsed.type = event;
  if (parsed.id === undefined && id !== undefined) parsed.id = id;
  return parsed;
}

/** Parse a whole recorded stream body (tests, `?once=1`). */
export function parseStream(body: string): StreamMessage[] {
  const parser = new SseParser();
  return parser.push(body.endsWith("\n\n") ? body : `${body}\n\n`);
}

/** Wait before the n-th reconnect (0-based): 1 s, 2 s, 4 s … capped at 15 s. */
export function backoff(attempt: number): number {
  return Math.min(15_000, 1000 * 2 ** Math.max(0, attempt));
}

export type ConnectionState = "idle" | "live" | "reconnecting";

export type FollowOptions = {
  url: string;
  /** The last stored seq applied; read on every (re)connect. */
  lastSeq: () => number;
  onMessage: (message: StreamMessage) => void;
  onState: (state: ConnectionState) => void;
  /** Asked when the server closes the stream: is the turn still running? */
  stillRunning: () => boolean;
  /** Called once the stream has ended for good (turn over, or stopped). */
  onEnd?: () => void;
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
};

/**
 * Follow a thread's stream until its turn ends. Returns a function that
 * stops following. Reconnects on a dropped connection with a capped backoff;
 * a refusal (4xx) ends the follow rather than retrying it.
 */
export function followThread(options: FollowOptions): () => void {
  const fetchImpl = options.fetchImpl ?? fetch;
  const sleep =
    options.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let stopped = false;
  let controller: AbortController | null = null;

  const run = async () => {
    let attempt = 0;
    while (!stopped) {
      controller = new AbortController();
      const after = options.lastSeq();
      const sep = options.url.includes("?") ? "&" : "?";
      const url = `${options.url}${sep}until_idle=1${after > 0 ? `&after=${after}` : ""}`;
      let refused = false;
      try {
        const response = await fetchImpl(url, {
          credentials: "include",
          cache: "no-store",
          headers: {
            Accept: "text/event-stream",
            ...(after > 0 ? { "Last-Event-ID": String(after) } : {}),
          },
          signal: controller.signal,
        });
        if (response.status >= 400 && response.status < 500) {
          refused = true;
        } else if (response.ok && response.body) {
          options.onState("live");
          attempt = 0;
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          const parser = new SseParser();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            for (const message of parser.push(decoder.decode(value, { stream: true }))) {
              options.onMessage(message);
            }
          }
        }
      } catch {
        // a network drop or our own abort: decided below
      }
      if (stopped) break;
      if (refused || !options.stillRunning()) break;
      options.onState("reconnecting");
      await sleep(backoff(attempt));
      attempt += 1;
    }
    options.onState("idle");
    if (!stopped) options.onEnd?.();
  };

  void run();
  return () => {
    stopped = true;
    controller?.abort();
  };
}
