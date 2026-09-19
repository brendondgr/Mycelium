"use client";

import * as React from "react";

import { AmbientSettingsCard } from "@/components/portal/ambient/ambient-settings-card";
import { Card } from "@/components/portal/primitives/card";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { TabBar, type TabItem } from "@/components/portal/primitives/tab-bar";
import {
  useAnswerSuggestion,
  useChanges,
  useDeleteUnderstanding,
  useEditUnderstanding,
  useReopenUnderstanding,
  useSuggestions,
  useUnderstanding,
  useUndoChange,
} from "@/lib/portal/ambient/hooks";
import type {
  Change,
  Development,
  Suggestion,
  UnderstandingEdge,
} from "@/lib/portal/ambient/types";

type TabKey = "answer" | "changed" | "declined" | "knows" | "settings";

/**
 * "Mylo & you" (ambient Plan 07): what Mylo noticed in your conversations and
 * wants to check, what changed and why, what you declined or let fade, and
 * everything it knows about you — each thing editable, deletable, undoable.
 *
 * Nothing here is anybody's words: Mylo keeps its own short summaries, and the
 * page says so. Nothing Mylo understood changes a recommendation until you
 * say yes, and what it learned from conversation is seen by nobody else.
 */
export function MyloAndYouSection() {
  const suggestions = useSuggestions();
  const [tab, setTab] = React.useState<TabKey>("answer");
  const open = suggestions.data?.suggestions.length ?? 0;
  const items: TabItem[] = [
    { key: "answer", label: "Needs your answer", badge: open ? <Count n={open} /> : undefined },
    { key: "changed", label: "What changed" },
    { key: "declined", label: "Faded and declined" },
    { key: "knows", label: "What Mylo knows" },
    { key: "settings", label: "Settings" },
  ];
  return (
    <div data-ambient="mylo-and-you">
      <SectionHeader
        eyebrow="Workspace"
        title="Mylo & you"
        subtitle="What Mylo noticed in your conversations, what changed, and what it knows. Nothing changes a recommendation until you say yes."
      />
      <TabBar
        items={items}
        active={tab}
        onChange={(key) => setTab(key as TabKey)}
        ariaLabel="Mylo and you"
        panelId="mylo-panel"
        idPrefix="mylo-tab"
        className="mb-5"
      />
      <div
        role="tabpanel"
        id="mylo-panel"
        aria-labelledby={`mylo-tab-${tab}`}
        tabIndex={0}
        className="focus-visible:outline-none"
      >
        {tab === "answer" ? (
          <NeedsAnswer query={suggestions} />
        ) : tab === "changed" ? (
          <WhatChanged />
        ) : tab === "declined" ? (
          <FadedAndDeclined />
        ) : tab === "knows" ? (
          <WhatMyloKnows />
        ) : (
          <AmbientSettingsCard />
        )}
      </div>
    </div>
  );
}

function Count({ n }: { n: number }) {
  return (
    <span className="ml-1.5 rounded-full bg-primary px-1.5 text-[11px] font-semibold text-[#fffdf8]">
      {n}
    </span>
  );
}

function Quiet({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-2xl border border-dashed border-border bg-surface px-6 py-10 text-center text-sm text-[var(--text-secondary)]">
      {children}
    </p>
  );
}

function Loading() {
  return <p className="text-sm text-[var(--text-secondary)]">Loading…</p>;
}

function Failed({ what }: { what: string }) {
  return <p className="text-sm text-clay">Couldn&apos;t load {what}. Try again in a moment.</p>;
}

/** Mylo's own `**bold**` for the topic; nothing else is formatted. */
function Plain({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={index} className="font-semibold text-[var(--text-primary)]">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        ),
      )}
    </>
  );
}

function when(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// -- needs your answer ------------------------------------------------------------

type Answered = { id: number; message: string };

function NeedsAnswer({ query }: { query: ReturnType<typeof useSuggestions> }) {
  // Mylo's reply outlives the question: the answered card leaves the list on
  // refetch, so the reply is kept here, in a live region (EXP-2026-09-016).
  const [answered, setAnswered] = React.useState<Answered[]>([]);
  if (query.isLoading) return <Loading />;
  if (query.isError) return <Failed what="Mylo's questions" />;
  const done = new Set(answered.map((row) => row.id));
  const rows = (query.data?.suggestions ?? []).filter((row) => !done.has(row.id));
  return (
    <div className="space-y-3.5">
      <div role="status" aria-live="polite" className="space-y-2 empty:hidden">
        {answered.map((row) => (
          <p
            key={row.id}
            className="rounded-lg border border-border bg-surface-alt/60 px-3.5 py-2.5 text-sm text-[var(--text-primary)]"
          >
            <Plain text={row.message} />
          </p>
        ))}
      </div>
      {rows.length ? (
        rows.map((suggestion) => (
          <SuggestionCard
            key={suggestion.id}
            suggestion={suggestion}
            onAnswered={(message) =>
              setAnswered((prev) => [{ id: suggestion.id, message }, ...prev])
            }
          />
        ))
      ) : (
        <Quiet>
          Nothing pending. Mylo will ask here or on Discord when it notices something worth
          checking.
        </Quiet>
      )}
    </div>
  );
}

function SuggestionCard({
  suggestion,
  onAnswered,
}: {
  suggestion: Suggestion;
  onAnswered: (message: string) => void;
}) {
  const answer = useAnswerSuggestion();
  const [error, setError] = React.useState<string | null>(null);
  const [rewording, setRewording] = React.useState(false);
  const [correction, setCorrection] = React.useState("");
  const yesLike = suggestion.choices.filter((c) => !["later", "no"].includes(c.key));
  const choose = (choice: string, fix?: string) => {
    answer.mutate(
      { id: suggestion.id, choice, correction: fix },
      {
        onSuccess: (result) => onAnswered(result.message),
        onError: (failure) => setError(failure.message),
      },
    );
  };
  return (
    <Card className="p-[18px]">
      <p className="text-[11.5px] font-semibold uppercase tracking-[0.04em] text-[var(--text-secondary)]">
        {suggestion.project ? suggestion.project.name : "About you"}
      </p>
      <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-[var(--text-secondary)]">
        <Plain text={suggestion.question} />
      </p>
      {error ? (
        <p role="alert" className="mt-3 text-sm text-clay">
          {error}
        </p>
      ) : null}
      <>
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={`Answer about ${suggestion.topic}`}>
            {suggestion.choices.map((choice, index) => (
              <button
                key={choice.key}
                type="button"
                disabled={answer.isPending}
                onClick={() => choose(choice.key)}
                className={
                  index === 0
                    ? "rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-[#fffdf8] disabled:opacity-60"
                    : "rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
                }
              >
                {choice.label}
              </button>
            ))}
          </div>
          {["interest", "skill"].includes(suggestion.kind) && yesLike.length ? (
            rewording ? (
              <form
                className="mt-3 flex flex-wrap items-end gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (correction.trim()) choose(yesLike[0].key, correction.trim());
                }}
              >
                <label className="text-sm text-[var(--text-primary)]">
                  <span className="block text-xs text-[var(--text-secondary)]">Call it</span>
                  <input
                    value={correction}
                    onChange={(event) => setCorrection(event.target.value)}
                    maxLength={200}
                    className="mt-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                  />
                </label>
                <button
                  type="submit"
                  disabled={!correction.trim() || answer.isPending}
                  className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
                >
                  Yes, with this name
                </button>
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setRewording(true)}
                className="mt-2 text-sm font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
              >
                Right idea, wrong words?
              </button>
            )
          ) : null}
          <p className="mt-3 text-[12px] text-[var(--text-secondary)]">
            Asked {when(suggestion.asked_at) || "today"} · closes {when(suggestion.expires_at)} ·
            answering here closes it on Discord too.
          </p>
        </>
    </Card>
  );
}

// -- what changed -------------------------------------------------------------------

const SURFACE: Record<string, string> = {
  dm: "you confirmed on Discord",
  web: "you confirmed here",
  told: "you told Mylo",
};

function WhatChanged() {
  const changes = useChanges();
  const [filter, setFilter] = React.useState<"all" | "you" | "projects">("all");
  if (changes.isLoading) return <Loading />;
  if (changes.isError) return <Failed what="what changed" />;
  const rows = (changes.data?.changes ?? []).filter((row) =>
    filter === "all" ? true : filter === "projects" ? Boolean(row.project) : !row.project,
  );
  return (
    <div>
      <label className="mb-3 inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
        Show
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as typeof filter)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-[var(--text-primary)]"
        >
          <option value="all">Everything</option>
          <option value="you">About you</option>
          <option value="projects">Your projects</option>
        </select>
      </label>
      {rows.length ? (
        <ul className="space-y-3">
          {rows.map((row) => (
            <ChangeRow key={row.id} change={row} />
          ))}
        </ul>
      ) : (
        <Quiet>
          Nothing has changed yet. When you say yes to something Mylo asked, or tell it a fact
          about a project, it shows up here with an undo.
        </Quiet>
      )}
    </div>
  );
}

function ChangeRow({ change }: { change: Change }) {
  const undo = useUndoChange();
  const [error, setError] = React.useState<string | null>(null);
  const how =
    change.kind === "undone"
      ? `Undone by ${change.by.you ? "you" : change.by.name}`
      : change.by.you
        ? SURFACE[change.surface] ?? ""
        : `${change.by.name} confirmed`;
  return (
    <li>
      <Card className="p-[16px]">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.04em] text-[var(--text-secondary)]">
              {change.kind_label}
              {change.project ? ` · ${change.project.name}` : ""}
            </p>
            <p className="mt-0.5 font-medium text-[var(--text-primary)]">{change.topic}</p>
            <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">
              {when(change.created_at)}
              {how ? ` · ${how}` : ""}
              {change.undone_at ? ` · undone ${when(change.undone_at)}` : ""}
            </p>
          </div>
          {change.can_undo ? (
            <button
              type="button"
              disabled={undo.isPending}
              aria-label={`Undo: ${change.topic}`}
              onClick={() =>
                undo.mutate(change.id, { onError: (e) => setError(e.message) })
              }
              className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
            >
              Undo
            </button>
          ) : null}
        </div>
        {change.explanation ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-sm text-[var(--text-secondary)]">Why?</summary>
            <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
              {change.explanation}
            </p>
          </details>
        ) : null}
        {error ? <p className="mt-2 text-sm text-clay">{error}</p> : null}
      </Card>
    </li>
  );
}

// -- faded and declined -------------------------------------------------------------

function FadedAndDeclined() {
  const knows = useUnderstanding();
  const reopen = useReopenUnderstanding();
  if (knows.isLoading) return <Loading />;
  if (knows.isError) return <Failed what="this" />;
  const rows = (knows.data?.edges ?? []).filter(
    (edge) => edge.tier === "conversational" && ["faded", "rejected"].includes(edge.status),
  );
  if (!rows.length) {
    return (
      <Quiet>
        Nothing here. Things you say no to, and explorations you stop coming back to, rest here
        where you can reopen them.
      </Quiet>
    );
  }
  return (
    <ul className="space-y-3">
      {rows.map((edge) => (
        <li key={`${edge.concept_id}-${edge.relation}`}>
          <Card className="flex flex-wrap items-center justify-between gap-2 p-[16px]">
            <div className="min-w-0">
              <p className="font-medium text-[var(--text-primary)]">{edge.label}</p>
              <p className="text-[12px] text-[var(--text-secondary)]">
                {edge.status === "faded"
                  ? "Faded — you hadn't come back to it."
                  : edge.resting
                    ? `You said no. Mylo won't ask before ${when(edge.eligible_again_on)}, and then only if you keep coming back to it.`
                    : "You said no. Mylo asks again only if you keep coming back to it."}
              </p>
            </div>
            <button
              type="button"
              disabled={reopen.isPending}
              aria-label={`Include ${edge.label} after all`}
              onClick={() => reopen.mutate({ conceptId: edge.concept_id, relation: edge.relation })}
              className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
            >
              Include it after all
            </button>
          </Card>
        </li>
      ))}
    </ul>
  );
}

// -- what Mylo knows ------------------------------------------------------------------

const KIND_LABEL: Record<string, string> = {
  enduring_interest: "Interest",
  current_curiosity: "Exploring",
  work_preference: "How you like to work",
  career_direction: "Where you're heading",
  capability: "Skill",
  learning_goal: "Learning",
};

function WhatMyloKnows() {
  const knows = useUnderstanding();
  if (knows.isLoading) return <Loading />;
  if (knows.isError || !knows.data) return <Failed what="what Mylo knows" />;
  const { edges, developments, statement } = knows.data;
  const groups: { title: string; rows: UnderstandingEdge[] }[] = [
    {
      title: "From conversation",
      rows: edges.filter((e) => e.tier === "conversational" && ["active", "pending"].includes(e.status)),
    },
    { title: "You wrote this", rows: edges.filter((e) => e.tier === "declared") },
    { title: "Your papers show this", rows: edges.filter((e) => e.tier === "demonstrated") },
  ];
  return (
    <div className="space-y-6">
      <p className="max-w-[70ch] text-sm leading-relaxed text-[var(--text-secondary)]">
        {statement} What Mylo learned from conversation is seen by nobody else and never makes
        you findable.
      </p>
      {groups.map((group) => (
        <section key={group.title} aria-label={group.title}>
          <h2 className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
            {group.title}
          </h2>
          {group.rows.length ? (
            <ul className="mt-2 space-y-2">
              {group.rows.map((edge) => (
                <KnownRow key={`${edge.tier}-${edge.concept_id}-${edge.relation}`} edge={edge} />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[var(--text-secondary)]">Nothing yet.</p>
          )}
        </section>
      ))}
      <section aria-label="Your projects">
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
          Your projects
        </h2>
        {developments.length ? (
          <ul className="mt-2 space-y-2">
            {developments.map((row) => (
              <DevelopmentRow key={row.id} row={row} />
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            No project developments yet. Tell Mylo when something changes — data arrives, a
            deadline moves — and it will note it here.
          </p>
        )}
      </section>
    </div>
  );
}

function KnownRow({ edge }: { edge: UnderstandingEdge }) {
  const edit = useEditUnderstanding();
  const remove = useDeleteUnderstanding();
  const [editing, setEditing] = React.useState(false);
  const [label, setLabel] = React.useState(edge.label);
  const tag =
    edge.tier !== "conversational"
      ? edge.source
      : edge.status === "pending"
        ? "Waiting for your answer"
        : edge.edited
          ? "Your wording"
          : `Confirmed · since ${when(edge.first_seen)}`;
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2.5 text-sm">
      {editing ? (
        <form
          className="flex flex-1 flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            edit.mutate(
              { conceptId: edge.concept_id, relation: edge.relation, label },
              { onSuccess: () => setEditing(false) },
            );
          }}
        >
          <label className="sr-only" htmlFor={`edit-${edge.concept_id}-${edge.relation}`}>
            New wording
          </label>
          <input
            id={`edit-${edge.concept_id}-${edge.relation}`}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            maxLength={200}
            className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm"
          />
          <button type="submit" className="rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-[#fffdf8]">
            Save
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-sm text-[var(--text-secondary)] underline-offset-2 hover:underline"
          >
            Cancel
          </button>
        </form>
      ) : (
        <>
          <div className="min-w-0">
            <span className="font-medium text-[var(--text-primary)]">{edge.label}</span>
            {edge.kind ? (
              <span className="ml-2 text-[12px] text-[var(--text-secondary)]">
                {KIND_LABEL[edge.kind] ?? edge.kind}
              </span>
            ) : null}
            <span className="ml-2 text-[12px] text-[var(--text-secondary)]">· {tag}</span>
          </div>
          {edge.editable ? (
            <div className="flex gap-2">
              <button
                type="button"
                aria-label={`Edit ${edge.label}`}
                onClick={() => setEditing(true)}
                className="text-sm font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
              >
                Edit
              </button>
              <button
                type="button"
                disabled={remove.isPending}
                aria-label={`Delete ${edge.label}`}
                onClick={() => remove.mutate({ conceptId: edge.concept_id, relation: edge.relation })}
                className="text-sm font-medium text-clay underline-offset-2 hover:underline"
              >
                Delete
              </button>
            </div>
          ) : null}
        </>
      )}
    </li>
  );
}

export function DevelopmentRow({ row }: { row: Development }) {
  return (
    <li className="rounded-lg border border-border px-3 py-2.5 text-sm">
      <p className="text-[12px] text-[var(--text-secondary)]">
        {when(row.occurred_on)} · {row.project.name} · {row.change_label}
        {row.status === "pending" ? " · waiting for a confirmation" : ""}
        {row.visibility === "personal" ? " · only you see this" : ""}
      </p>
      <p className="mt-0.5 text-[var(--text-primary)]">{row.account}</p>
      {row.explanation ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-[12px] text-[var(--text-secondary)]">
            How Mylo knows
          </summary>
          <p className="mt-1 text-[12.5px] text-[var(--text-secondary)]">{row.explanation}</p>
        </details>
      ) : null}
    </li>
  );
}
