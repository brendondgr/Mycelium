"use client";

import { useAgentThreads } from "@/lib/portal/hooks";
import type { AgentThread } from "@/lib/portal/agent/types";

/** The conversation list: pinned first, then most recent. */
export function HistoryList({
  currentId,
  onPick,
}: {
  currentId: string | null;
  onPick: (thread: AgentThread) => void;
}) {
  const threads = useAgentThreads();
  if (threads.isLoading) return <p className="ws-mylo-aside ws-mylo-pad">Loading…</p>;
  if (threads.isError) return <p className="ws-mylo-aside ws-mylo-pad">Could not load your conversations.</p>;
  const rows = threads.data ?? [];
  if (!rows.length) return <p className="ws-mylo-aside ws-mylo-pad">No conversations yet.</p>;
  return (
    <ul className="ws-mylo-history">
      {rows.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            className="ws-mylo-history-row"
            aria-current={t.id === currentId || undefined}
            onClick={() => onPick(t)}
          >
            <span className="ws-mylo-history-title">{t.title || "Untitled chat"}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
