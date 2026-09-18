"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Card } from "@/components/portal/primitives/card";
import { useProjectConversation } from "@/lib/portal/hooks";
import { correctAttribution, setChannelHint } from "@/lib/portal/mutations";
import type {
  AttributionEntry,
  Project,
  ProjectConversation,
} from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/**
 * What Mylo filed under this project from the lab's own conversation, and the
 * two ways an editor can steer it: a channel hint, and "this was about a
 * different project".
 *
 * Nothing here shows what anybody said, because nothing is kept. An entry is
 * when, where, who, how sure Mylo was, and which of the *project's* own words
 * it matched — enough to judge whether it filed the message correctly, and no
 * more. A correction is the editor's answer and it outranks Mylo's.
 */

const NOT_A_PROJECT = "__none__";

const PILL =
  "rounded-full border border-border bg-surface px-3.5 py-1.5 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function place(entry: AttributionEntry): string {
  if (entry.place_kind === "dm") return "a direct message";
  const label = entry.place_label ? `#${entry.place_label}` : "a channel";
  if (entry.place_kind === "thread") return `a thread in ${label}`;
  if (entry.place_kind === "forum") return `a forum post, ${label}`;
  return label;
}

function why(entry: AttributionEntry): string {
  if (entry.corrected) return "A person filed this here.";
  const sure =
    entry.confidence == null ? "" : `${Math.round(entry.confidence * 100)}% sure`;
  if (entry.matched.length) {
    const terms = entry.matched.map((term) => `“${term}”`).join(", ");
    return `${sure ? `${sure} — ` : ""}matched ${terms}.`;
  }
  return sure
    ? `${sure} — carried from the conversation around it.`
    : "Carried from the conversation around it.";
}

function AttributionRow({
  entry,
  alternatives,
  onMove,
  busy,
}: {
  entry: AttributionEntry;
  alternatives: ProjectConversation["alternatives"];
  onMove: (entry: AttributionEntry, target: string | null) => void;
  busy: boolean;
}) {
  const [target, setTarget] = React.useState("");
  const selectId = `move-attribution-${entry.id}`;
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <p className="text-[13px] text-[var(--text-primary)]">
        <span className="font-semibold">{entry.speaker.name}</span>
        <span className="text-[var(--text-secondary)]">
          {" "}
          in {place(entry)} · {when(entry.sent_at)}
        </span>
      </p>
      <p className="mt-0.5 text-[12.5px] leading-5 text-[var(--text-secondary)]">
        {why(entry)}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label htmlFor={selectId} className="sr-only">
          Move this to a different project
        </label>
        <select
          id={selectId}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          disabled={busy}
          className="min-h-[36px] max-w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[12.5px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Different project…</option>
          {alternatives.map((one) => (
            <option key={one.id} value={one.id}>
              {one.name}
            </option>
          ))}
          <option value={NOT_A_PROJECT}>Not about a project</option>
        </select>
        <button
          type="button"
          disabled={busy || !target}
          onClick={() => onMove(entry, target === NOT_A_PROJECT ? null : target)}
          className={PILL}
        >
          Move
        </button>
      </div>
    </li>
  );
}

function ChannelHints({
  project,
  data,
  onToggle,
  busy,
}: {
  project: Project;
  data: ProjectConversation;
  onToggle: (placeId: string, on: boolean) => void;
  busy: boolean;
}) {
  if (!data.channels.length) {
    return (
      <p className="text-[12.5px] leading-5 text-[var(--text-secondary)]">
        No channels yet. A channel appears here once someone who has opted in
        speaks in it.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {data.channels.map((channel) => {
        const mine = channel.hinted_project?.id === project.id;
        const elsewhere = channel.hinted_project && !mine;
        return (
          <li
            key={channel.place_id}
            className="flex items-center justify-between gap-3 rounded-lg bg-surface-alt px-3 py-2"
          >
            <span className="min-w-0 text-[13px] text-[var(--text-primary)]">
              <span className="font-medium">#{channel.label || "channel"}</span>
              {elsewhere ? (
                <span className="block text-[11.5px] text-[var(--text-muted)]">
                  Points at {channel.hinted_project?.name}
                </span>
              ) : null}
            </span>
            <button
              type="button"
              aria-pressed={mine}
              disabled={busy}
              onClick={() => onToggle(channel.place_id, !mine)}
              className={cn(
                "shrink-0 rounded-full border px-3 py-1.5 text-[12px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
                mine
                  ? "border-primary bg-primary text-[#fffdf8]"
                  : "border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt",
              )}
            >
              {mine ? "Points here" : "Point here"}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function ProjectConversationCard({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const query = useProjectConversation(project.id, project.can_edit);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  if (!project.can_edit) return null;

  const key = ["portal", "project-conversation", project.id];

  async function run(action: () => Promise<unknown>, done: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: key });
      setNotice(done);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save that. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (query.isLoading) {
    return (
      <Card className="animate-pulse p-[22px]" aria-busy="true">
        <span className="block h-3 w-32 rounded bg-surface-alt" />
        <span className="mt-4 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-2/3 rounded bg-surface-alt" />
      </Card>
    );
  }

  const data = query.data;
  if (query.isError || !data) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-[3px] text-[15px] font-semibold text-[var(--text-primary)]">
          In conversation
        </h2>
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Couldn&apos;t load what Mylo filed under this project.
        </p>
      </Card>
    );
  }

  const isLab = data.scope === "lab";
  const nameFor = (id: string | null) =>
    id === null
      ? "not about a project"
      : data.alternatives.find((one) => one.id === id)?.name ?? "that project";

  return (
    <Card className="p-[22px]">
      <h2 className="mb-[3px] text-[15px] font-semibold text-[var(--text-primary)]">
        In conversation
      </h2>
      <p className="mb-[14px] text-[12.5px] leading-5 text-[var(--text-secondary)]">
        {isLab
          ? "Messages from your lab's Discord that Mylo filed under this project. Mylo keeps no messages — only when, where, who, and which of this project's names it matched. When it isn't sure, it files nothing."
          : "Your own messages that Mylo filed under this project. Mylo keeps no messages — only when, where, and which of this project's names it matched."}
      </p>

      {isLab && !data.listening && data.attributions.length === 0 ? (
        <p className="text-[12.5px] leading-5 text-[var(--text-secondary)]">
          Mylo isn&apos;t listening in this lab&apos;s Discord server. A lab
          manager can turn it on with <code>/setup</code> in the server; each
          member then chooses for themselves.
        </p>
      ) : null}

      {isLab && data.listening ? (
        <section className="mb-[18px]" aria-labelledby={`hints-${project.id}`}>
          <h3
            id={`hints-${project.id}`}
            className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]"
          >
            Channels
          </h3>
          <p className="mb-2 text-[12px] leading-5 text-[var(--text-muted)]">
            Pointing a channel here nudges Mylo toward this project there. It
            never decides on its own — what people actually say still does.
          </p>
          <ChannelHints
            project={project}
            data={data}
            busy={busy}
            onToggle={(placeId, on) =>
              void run(
                () => setChannelHint(project.id, placeId, on),
                on ? "Channel now points here." : "Channel no longer points here.",
              )
            }
          />
        </section>
      ) : null}

      {data.attributions.length ? (
        <section aria-labelledby={`recent-${project.id}`}>
          <h3
            id={`recent-${project.id}`}
            className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]"
          >
            Recently filed here
          </h3>
          <ul className="divide-y divide-[var(--divider)]">
            {data.attributions.map((entry) => (
              <AttributionRow
                key={entry.id}
                entry={entry}
                alternatives={data.alternatives}
                busy={busy}
                onMove={(row, target) =>
                  void run(
                    () => correctAttribution(row.id, target),
                    `Moved — ${nameFor(target)}.`,
                  )
                }
              />
            ))}
          </ul>
        </section>
      ) : data.listening || !isLab ? (
        <p className="text-[12.5px] leading-5 text-[var(--text-secondary)]">
          Nothing filed under this project yet. When people who have opted in
          talk about it — by name, or by one of its aliases — it will appear
          here.
        </p>
      ) : null}

      <p className="mt-3 text-[12px] text-[var(--text-secondary)]" aria-live="polite">
        {notice}
      </p>
      {error ? (
        <p className="mt-1 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
