"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import {
  AgentError,
  agentUrl,
  answerQuestion,
  cancelTurn,
  createThread,
  fetchThreadEvents,
  sendMessage,
  type NewThread,
} from "./client";
import { followThread, type ConnectionState } from "./stream";
import { apply, applyAll, emptyView, fromEvent, type ThreadView } from "./turns";
import type { AgentRefusal, AgentThread } from "./types";

/**
 * One conversation, live: its turn model, the stream that keeps it current
 * while a turn runs, and the three things a person can do to it (send,
 * answer, stop).
 *
 * `threadId` null is a conversation not yet stored: nothing is written until
 * the first message is sent (opening and closing the panel leaves nothing in
 * history). `draft` says what to create then — its scope and anchor.
 *
 * Mount it once per conversation (key its component by conversation): the
 * only id change it follows is a draft becoming the thread it created.
 */
export function useThreadRuntime({
  threadId,
  draft,
  onCreated,
}: {
  threadId: string | null;
  draft: NewThread;
  onCreated: (thread: AgentThread) => void;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = React.useState<ThreadView>(() => emptyView());
  const viewRef = React.useRef(view);
  const [loading, setLoading] = React.useState(Boolean(threadId));
  const [loadError, setLoadError] = React.useState<AgentRefusal | null>(null);
  const [connection, setConnection] = React.useState<ConnectionState>("idle");
  const [queued, setQueued] = React.useState<string[]>([]);
  const [sendError, setSendError] = React.useState<{ refusal: AgentRefusal; text: string } | null>(null);
  const [sending, setSending] = React.useState(false);
  const stopRef = React.useRef<(() => void) | null>(null);
  const idRef = React.useRef(threadId);
  /** The id this hook just created, so adopting it does not reload it. */
  const createdRef = React.useRef<string | null>(null);

  const commit = React.useCallback((next: ThreadView) => {
    viewRef.current = next;
    setView(next);
  }, []);

  const refreshLists = React.useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["agent", "threads"] });
    if (idRef.current) {
      void queryClient.invalidateQueries({ queryKey: ["agent", "thread", idRef.current] });
    }
  }, [queryClient]);

  const stopFollowing = React.useCallback(() => {
    stopRef.current?.();
    stopRef.current = null;
  }, []);

  /** Follow the stream until the running turn ends. */
  const follow = React.useCallback(
    (id: string) => {
      if (stopRef.current) return;
      stopRef.current = followThread({
        url: agentUrl("threads", id, "stream"),
        lastSeq: () => viewRef.current.lastSeq,
        onMessage: (message) => {
          if (idRef.current !== id) return;
          const next = apply(viewRef.current, message);
          if (next === viewRef.current) return;
          if (message.type === "user") {
            const text = String(message.payload?.text ?? "");
            setQueued((q) => {
              const at = q.indexOf(text);
              return at >= 0 ? [...q.slice(0, at), ...q.slice(at + 1)] : q;
            });
          }
          commit(next);
        },
        onState: setConnection,
        stillRunning: () => viewRef.current.state === "running",
        onEnd: () => {
          stopRef.current = null;
          refreshLists();
        },
      });
    },
    [commit, refreshLists],
  );

  /** Read whatever was stored after what we have (the tail), then follow if it runs. */
  const catchUp = React.useCallback(
    async (id: string) => {
      const data = await fetchThreadEvents(id, viewRef.current.lastSeq);
      if (idRef.current !== id) return;
      const next = applyAll(viewRef.current, data.events.map(fromEvent));
      commit({ ...next, state: data.state });
      if (data.state === "running") follow(id);
    },
    [commit, follow],
  );

  // Load the conversation once. The caller keys this hook's component by
  // conversation, so switching to another one starts a fresh hook; the only
  // id change seen here is a draft becoming the thread it just created.
  React.useEffect(() => {
    if (!threadId || createdRef.current === threadId) return;
    let live = true;
    catchUp(threadId)
      .catch((error) => {
        if (live) {
          setLoadError(
            error instanceof AgentError
              ? error.refusal
              : { code: "error", detail: "Could not load this conversation.", fix: "" },
          );
        }
      })
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [threadId, catchUp]);

  React.useEffect(() => () => stopFollowing(), [stopFollowing]);

  // Stale: a conversation changed in another tab reloads its tail on focus.
  React.useEffect(() => {
    if (!threadId) return;
    const onFocus = () => {
      if (document.visibilityState !== "visible" || stopRef.current) return;
      catchUp(threadId).catch(() => {});
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [threadId, catchUp]);

  const send = React.useCallback(
    async (text: string, mentions: string[] = []) => {
      const clean = text.trim();
      if (!clean) return;
      setSendError(null);
      setSending(true);
      try {
        let id = idRef.current;
        if (!id) {
          const thread = await createThread(draft);
          id = thread.id;
          idRef.current = id;
          createdRef.current = id;
          queryClient.setQueryData(["agent", "thread", id], thread);
          onCreated(thread);
        }
        const result = await sendMessage(id, clean, mentions);
        if (result.status === "queued") setQueued((q) => [...q, clean]);
        commit({ ...viewRef.current, state: "running" });
        follow(id);
        refreshLists();
      } catch (error) {
        setSendError({
          text: clean,
          refusal:
            error instanceof AgentError
              ? error.refusal
              : { code: "error", detail: "Mylo did not get that message.", fix: "" },
        });
      } finally {
        setSending(false);
      }
    },
    [commit, draft, follow, onCreated, queryClient, refreshLists],
  );

  const answer = React.useCallback(
    async (text: string) => {
      const id = idRef.current;
      if (!id || !text.trim()) return;
      setSendError(null);
      try {
        await answerQuestion(id, text.trim());
        commit({ ...viewRef.current, state: "running" });
        follow(id);
      } catch (error) {
        setSendError({
          text: "",
          refusal:
            error instanceof AgentError
              ? error.refusal
              : { code: "error", detail: "Mylo did not get that answer.", fix: "" },
        });
      }
    },
    [commit, follow],
  );

  const cancel = React.useCallback(async () => {
    const id = idRef.current;
    if (!id) return;
    setQueued([]);
    try {
      await cancelTurn(id);
    } catch {
      // the turn ends on its own; nothing to show
    }
  }, []);

  return {
    view,
    loading,
    loadError,
    connection,
    queued,
    sending,
    sendError,
    clearSendError: () => setSendError(null),
    send,
    answer,
    cancel,
  };
}

export type ThreadRuntime = ReturnType<typeof useThreadRuntime>;
