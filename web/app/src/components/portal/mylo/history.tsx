"use client";

import * as React from "react";
import { Archive, ArchiveRestore, Pencil, Pin, Search, Trash2 } from "lucide-react";

import type { AgentThread } from "@/lib/portal/agent/types";
import {
  useAgentThreads,
  useDeleteAgentThread,
  useUpdateAgentThread,
} from "@/lib/portal/hooks";

/**
 * The conversation list, in place of the conversation: a search, then pinned
 * first and the rest by last activity (the server's order). Each row can be
 * renamed, pinned, archived or deleted. Archived conversations leave the list
 * and come back under "Archived".
 */
export function HistoryList({
  currentId,
  onPick,
  onDeleted,
}: {
  currentId: string | null;
  onPick: (thread: AgentThread) => void;
  onDeleted?: (id: string) => void;
}) {
  const [q, setQ] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [archived, setArchived] = React.useState(false);
  const searchId = React.useId();

  // search as the person types, without a request per keystroke
  React.useEffect(() => {
    const t = window.setTimeout(() => setQuery(q), 250);
    return () => window.clearTimeout(t);
  }, [q]);

  const threads = useAgentThreads({ q: query, archived });
  const rows = threads.data ?? [];

  return (
    <div className="ws-mylo-history-view">
      <div className="ws-mylo-history-search">
        <Search size={14} aria-hidden="true" />
        <label htmlFor={searchId} className="ws-sr">
          Search conversations
        </label>
        <input
          id={searchId}
          type="search"
          value={q}
          placeholder="Search conversations"
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="ws-mylo-history-tabs" role="group" aria-label="Which conversations">
        <button type="button" aria-pressed={!archived} onClick={() => setArchived(false)}>
          Recent
        </button>
        <button type="button" aria-pressed={archived} onClick={() => setArchived(true)}>
          Archived
        </button>
      </div>
      {threads.isLoading ? (
        <div className="ws-mylo-skeleton ws-mylo-pad" aria-hidden="true">
          <span className="ws-skel" style={{ width: "70%" }} />
          <span className="ws-skel" style={{ width: "55%" }} />
          <span className="ws-skel" style={{ width: "62%" }} />
        </div>
      ) : threads.isError ? (
        <p className="ws-mylo-aside ws-mylo-pad" role="alert">
          Could not load your conversations.
        </p>
      ) : !rows.length ? (
        <p className="ws-mylo-aside ws-mylo-pad">
          {query
            ? "Nothing matches that."
            : archived
              ? "No archived conversations."
              : "No conversations yet. Ask Mylo something to start one."}
        </p>
      ) : (
        <ul className="ws-mylo-history" aria-label={archived ? "Archived conversations" : "Conversations"}>
          {rows.map((t) => (
            <HistoryRow
              key={t.id}
              thread={t}
              current={t.id === currentId}
              onPick={onPick}
              onDeleted={onDeleted}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function HistoryRow({
  thread,
  current,
  onPick,
  onDeleted,
}: {
  thread: AgentThread;
  current: boolean;
  onPick: (thread: AgentThread) => void;
  onDeleted?: (id: string) => void;
}) {
  const update = useUpdateAgentThread();
  const remove = useDeleteAgentThread();
  const [renaming, setRenaming] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [title, setTitle] = React.useState(thread.title);
  const name = thread.title || "Untitled chat";

  const saveTitle = () => {
    const next = title.trim();
    if (next && next !== thread.title) update.mutate({ id: thread.id, title: next });
    setRenaming(false);
  };

  if (confirming) {
    return (
      <li className="ws-mylo-history-item" data-confirm>
        <p className="ws-mylo-history-confirm">
          Delete “{name}”? This removes the conversation for good.
        </p>
        <div className="ws-mylo-history-confirm-actions">
          <button
            type="button"
            className="ws-mylo-chip"
            data-danger
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(thread.id, {
                onSuccess: () => onDeleted?.(thread.id),
              })
            }
          >
            Delete
          </button>
          <button type="button" className="ws-mylo-chip" autoFocus onClick={() => setConfirming(false)}>
            Keep
          </button>
        </div>
      </li>
    );
  }

  return (
    <li className="ws-mylo-history-item">
      {renaming ? (
        <input
          className="ws-mylo-title-input"
          aria-label="Conversation title"
          value={title}
          autoFocus
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              saveTitle();
            } else if (e.key === "Escape") {
              e.stopPropagation();
              setTitle(thread.title);
              setRenaming(false);
            }
          }}
          onBlur={saveTitle}
        />
      ) : (
        <button
          type="button"
          className="ws-mylo-history-row"
          aria-current={current || undefined}
          onClick={() => onPick(thread)}
        >
          {thread.pinned ? (
            <Pin size={12} aria-label="Pinned" className="ws-mylo-history-pin" />
          ) : null}
          <span className="ws-mylo-history-title">{name}</span>
          <time className="ws-mylo-history-when" dateTime={thread.last_activity_at}>
            {when(thread.last_activity_at)}
          </time>
        </button>
      )}
      <div className="ws-mylo-history-actions">
        <button
          type="button"
          className="ws-icon-btn"
          aria-label={`Rename ${name}`}
          title="Rename"
          onClick={() => {
            setTitle(thread.title);
            setRenaming(true);
          }}
        >
          <Pencil size={13} aria-hidden="true" />
        </button>
        {!thread.archived ? (
          <button
            type="button"
            className="ws-icon-btn"
            aria-label={thread.pinned ? `Unpin ${name}` : `Pin ${name}`}
            title={thread.pinned ? "Unpin" : "Pin"}
            aria-pressed={thread.pinned}
            onClick={() => update.mutate({ id: thread.id, pinned: !thread.pinned })}
          >
            <Pin size={13} aria-hidden="true" />
          </button>
        ) : null}
        <button
          type="button"
          className="ws-icon-btn"
          aria-label={thread.archived ? `Restore ${name}` : `Archive ${name}`}
          title={thread.archived ? "Restore" : "Archive"}
          onClick={() => update.mutate({ id: thread.id, archived: !thread.archived })}
        >
          {thread.archived ? (
            <ArchiveRestore size={13} aria-hidden="true" />
          ) : (
            <Archive size={13} aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          className="ws-icon-btn"
          aria-label={`Delete ${name}`}
          title="Delete"
          onClick={() => setConfirming(true)}
        >
          <Trash2 size={13} aria-hidden="true" />
        </button>
      </div>
    </li>
  );
}

/** "14:05" today, "Mon" this week, else "3 Nov". */
function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  if (now.getTime() - d.getTime() < 6 * 86_400_000) {
    return d.toLocaleDateString(undefined, { weekday: "short" });
  }
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
