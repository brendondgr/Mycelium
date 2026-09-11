"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { useProjectState } from "@/lib/portal/hooks";
import {
  confirmProjectState,
  extractProjectState,
  updateProjectState,
} from "@/lib/portal/mutations";
import type {
  Project,
  ProjectStateInput,
  ProjectStatePayload,
} from "@/lib/portal/types";
import { useQueryClient } from "@tanstack/react-query";

/**
 * What this project claims, what is blocking it, and what is due when.
 *
 * `goals` has always promised methods, datasets and deadlines and delivered a
 * display blob. This is where they actually live, and it is the input that lets a
 * report say something about *this project* rather than about a topic: whether a
 * paper just found tests the question this project asks, whether a dataset closes
 * one of its blockers, whether a venue's deadline is reachable from its next
 * milestone.
 *
 * Three things the surface owes the reader:
 *
 * **Stated versus inferred.** A badge on anything Mylo proposed and nobody has
 * accepted. A reader deciding what to do this week must be able to tell their own
 * words from a guess, and a guess that looks like a commitment is worse than no
 * guess at all.
 *
 * **A visible confirmation date.** State nobody has looked at in two months is
 * the most dangerous input the reports have, precisely because it reads as
 * current. The card says how long it has been and offers the one-click answer.
 *
 * **Inherit, not zero.** A blank timeline override means "use the lab's, or
 * mine", and the card says which one is actually in force rather than showing an
 * empty box that looks like a setting of nothing.
 */

const INPUT =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const LABEL =
  "mb-1 block text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]";

function InferredBadge() {
  return (
    <span
      title="Mylo proposed this and nobody has accepted it yet."
      className="ml-1.5 inline-block rounded-full border border-brand-accent px-1.5 py-px align-middle text-[10px] font-semibold uppercase tracking-wide text-brand-accent"
    >
      Inferred
    </span>
  );
}

function Field({
  label,
  inferred,
  children,
}: {
  label: string;
  inferred?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className={LABEL}>
        {label}
        {inferred ? <InferredBadge /> : null}
      </span>
      {children}
    </label>
  );
}

/** A comma-separated editor over a string list — the shape these fields are in. */
function ListField({
  label,
  inferred,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  inferred?: boolean;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  return (
    <Field label={label} inferred={inferred}>
      <input
        className={INPUT}
        value={value.join(", ")}
        placeholder={placeholder}
        onChange={(event) =>
          onChange(
            event.target.value
              .split(",")
              .map((part) => part.trim())
              .filter(Boolean),
          )
        }
      />
    </Field>
  );
}

function staleness(days: number | null): { text: string; warn: boolean } {
  if (days === null) return { text: "never confirmed", warn: true };
  if (days === 0) return { text: "confirmed today", warn: false };
  if (days === 1) return { text: "confirmed yesterday", warn: false };
  return { text: `confirmed ${days} days ago`, warn: days > 30 };
}

export function ProjectStateCard({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const query = useProjectState(project.id);
  const state = query.data;
  const canEdit = project.can_edit;

  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState<ProjectStateInput | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Reading a document proposes; it never writes. What comes back lands in the
  // open editor as a suggestion the reader edits or discards, because an
  // extractor that saved would overwrite what the team said with what a model
  // read — the one thing project state must never do.
  const [reading, setReading] = React.useState(false);
  const [readNote, setReadNote] = React.useState<string | null>(null);
  const fileInput = React.useRef<HTMLInputElement | null>(null);

  const invalidate = React.useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["portal", "project-state", project.id],
    });
  }, [queryClient, project.id]);

  function open(current: ProjectStatePayload) {
    setDraft({
      slow: {
        problem: current.slow.problem,
        claimed_contribution: current.slow.claimed_contribution,
        method: current.slow.method,
        data: current.slow.data,
        blockers: current.slow.blockers,
      },
      fast: {
        stage: current.fast.stage,
        milestones: current.fast.milestones,
        timeline_overrides: current.fast.timeline_overrides,
      },
    });
    setError(null);
    setEditing(true);
  }

  async function save() {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      await updateProjectState(project.id, draft);
      invalidate();
      setEditing(false);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function readDocument(file: File, current: ProjectStatePayload) {
    if (reading) return;
    setReading(true);
    setError(null);
    setReadNote(null);
    try {
      const result = await extractProjectState(project.id, file);
      if (!result.ok || !result.proposal?.slow) {
        setReadNote(
          result.reason ||
            "Mylo could not read a project out of that document.",
        );
        return;
      }
      const found = result.proposal;
      // Merged into whatever the editor already holds, and only where the
      // document actually said something: a blank answer must not wipe a line
      // the team typed a minute ago.
      setDraft((previous) => {
        const base = previous ?? {
          slow: current.slow,
          fast: current.fast,
        };
        return {
          slow: {
            ...base.slow,
            ...Object.fromEntries(
              Object.entries(found.slow ?? {}).filter(
                ([, value]) =>
                  value !== "" && !(Array.isArray(value) && value.length === 0),
              ),
            ),
          },
          fast: {
            ...base.fast,
            ...Object.fromEntries(
              Object.entries(found.fast ?? {}).filter(
                ([, value]) =>
                  value !== "" && !(Array.isArray(value) && value.length === 0),
              ),
            ),
          },
        };
      });
      setEditing(true);
      setReadNote(
        "Mylo filled in what the document said. Check it before saving — none of it is saved yet.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not read that document.",
      );
    } finally {
      setReading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await confirmProjectState(project.id);
      invalidate();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not confirm. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (query.isLoading) {
    return (
      <Card className="animate-pulse p-5">
        <span className="block h-3 w-32 rounded bg-surface-alt" />
        <span className="mt-4 block h-3 w-full rounded bg-surface-alt" />
        <span className="mt-2 block h-3 w-2/3 rounded bg-surface-alt" />
      </Card>
    );
  }
  if (!state) {
    return (
      <Card className="p-5">
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load this project&apos;s state.
        </p>
      </Card>
    );
  }

  const timeline = state.effective_timeline;
  const age = staleness(state.days_since_confirmed);
  const provenance = state.provenance;

  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          Project state
        </h2>
        {!state.is_empty ? (
          <span
            className={
              age.warn
                ? "text-[11.5px] font-medium text-clay"
                : "text-[11.5px] text-[var(--text-muted)]"
            }
          >
            {age.text}
          </span>
        ) : null}
      </div>

      {editing && draft ? (
        <div className="space-y-3.5">
          <Field label="What problem is this project answering?">
            <textarea
              className={`${INPUT} min-h-20 resize-y`}
              value={draft.slow?.problem ?? ""}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  slow: { ...draft.slow, problem: event.target.value },
                })
              }
            />
          </Field>
          <Field label="What is new about your answer?">
            <textarea
              className={`${INPUT} min-h-20 resize-y`}
              value={draft.slow?.claimed_contribution ?? ""}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  slow: {
                    ...draft.slow,
                    claimed_contribution: event.target.value,
                  },
                })
              }
            />
          </Field>
          <ListField
            label="Method"
            value={draft.slow?.method ?? []}
            placeholder="Comma-separated"
            onChange={(method) =>
              setDraft({ ...draft, slow: { ...draft.slow, method } })
            }
          />
          <ListField
            label="Data"
            value={draft.slow?.data ?? []}
            placeholder="Comma-separated"
            onChange={(data) =>
              setDraft({ ...draft, slow: { ...draft.slow, data } })
            }
          />
          <ListField
            label="What is blocking you?"
            value={(draft.slow?.blockers ?? []).map((b) => b.text)}
            placeholder="Comma-separated"
            onChange={(texts) =>
              setDraft({
                ...draft,
                slow: {
                  ...draft.slow,
                  blockers: texts.map((text, index) => ({
                    id: draft.slow?.blockers?.[index]?.id ?? "",
                    text,
                  })),
                },
              })
            }
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Stage">
              <input
                className={INPUT}
                value={draft.fast?.stage ?? ""}
                placeholder="experiments, writing, pitch hardening…"
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    fast: { ...draft.fast, stage: event.target.value },
                  })
                }
              />
            </Field>
            <Field label="Next milestone">
              <input
                className={INPUT}
                value={draft.fast?.milestones?.[0]?.what ?? ""}
                placeholder="MuSiQue pilot results"
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    fast: {
                      ...draft.fast,
                      milestones: [
                        {
                          id: draft.fast?.milestones?.[0]?.id ?? "",
                          kind:
                            draft.fast?.milestones?.[0]?.kind ?? "results_by",
                          what: event.target.value,
                          date: draft.fast?.milestones?.[0]?.date ?? "",
                          source: "stated",
                        },
                        ...(draft.fast?.milestones ?? []).slice(1),
                      ],
                    },
                  })
                }
              />
            </Field>
          </div>
          <Field label="Milestone date">
            <input
              type="date"
              className={INPUT}
              value={draft.fast?.milestones?.[0]?.date ?? ""}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  fast: {
                    ...draft.fast,
                    milestones: [
                      {
                        id: draft.fast?.milestones?.[0]?.id ?? "",
                        kind: draft.fast?.milestones?.[0]?.kind ?? "results_by",
                        what: draft.fast?.milestones?.[0]?.what ?? "",
                        date: event.target.value,
                        source: "stated",
                      },
                      ...(draft.fast?.milestones ?? []).slice(1),
                    ],
                  },
                })
              }
            />
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Deadline buffer (days)">
              <input
                type="number"
                min={0}
                max={90}
                className={INPUT}
                placeholder={`Inherit — ${timeline.buffer_days} (${timeline.buffer_source})`}
                value={draft.fast?.timeline_overrides?.deadline_buffer_days ?? ""}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    fast: {
                      ...draft.fast,
                      timeline_overrides: {
                        deadline_buffer_days:
                          event.target.value === ""
                            ? null
                            : Number(event.target.value),
                        min_paper_window_days:
                          draft.fast?.timeline_overrides
                            ?.min_paper_window_days ?? null,
                      },
                    },
                  })
                }
              />
            </Field>
            <Field label="Minimum paper window (days)">
              <input
                type="number"
                min={7}
                max={365}
                className={INPUT}
                placeholder={`Inherit — ${timeline.window_days} (${timeline.window_source})`}
                value={draft.fast?.timeline_overrides?.min_paper_window_days ?? ""}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    fast: {
                      ...draft.fast,
                      timeline_overrides: {
                        deadline_buffer_days:
                          draft.fast?.timeline_overrides
                            ?.deadline_buffer_days ?? null,
                        min_paper_window_days:
                          event.target.value === ""
                            ? null
                            : Number(event.target.value),
                      },
                    },
                  })
                }
              />
            </Field>
          </div>
          <p className="text-[11.5px] leading-5 text-[var(--text-muted)]">
            Leave either blank to inherit. Mylo currently judges this project
            against a {timeline.buffer_days}-day buffer ({timeline.buffer_source})
            and a {timeline.window_days}-day writing window (
            {timeline.window_source}).
          </p>

          {error ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}

          {readNote ? (
            <p className="text-[12.5px] text-[var(--text-secondary)]">{readNote}</p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {busy ? "Saving…" : "Save state"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
            >
              Cancel
            </button>
            <DocumentButton
              inputRef={fileInput}
              reading={reading}
              onPick={(file) => void readDocument(file, state)}
            />
          </div>
        </div>
      ) : state.is_empty ? (
        <div className="space-y-3">
          <p className="max-w-[52ch] text-[13.5px] leading-6 text-[var(--text-secondary)]">
            Mylo can only judge a paper against a topic until it knows what this
            project actually claims. Tell it what you are answering, what is new
            about your answer, and what is blocking you, and the reports start
            saying what to do rather than what exists.
          </p>
          {canEdit ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => open(state)}
                className="rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Describe this project
              </button>
              <DocumentButton
                inputRef={fileInput}
                reading={reading}
                onPick={(file) => void readDocument(file, state)}
              />
            </div>
          ) : null}
          {readNote ? (
            <p className="text-[12.5px] text-[var(--text-secondary)]">{readNote}</p>
          ) : null}
        </div>
      ) : (
        <div className="space-y-3 text-[13.5px] leading-6 text-[var(--text-primary)]">
          {state.slow.problem ? (
            <div>
              <span className={LABEL}>
                Problem
                {provenance.problem === "inferred" ? <InferredBadge /> : null}
              </span>
              <p>{state.slow.problem}</p>
            </div>
          ) : null}
          {state.slow.claimed_contribution ? (
            <div>
              <span className={LABEL}>
                Claimed contribution
                {provenance.claimed_contribution === "inferred" ? (
                  <InferredBadge />
                ) : null}
              </span>
              <p>{state.slow.claimed_contribution}</p>
            </div>
          ) : null}
          {state.fast.milestones.length ? (
            <div>
              <span className={LABEL}>Next milestone</span>
              <p>
                {state.fast.milestones[0].what}
                {state.fast.milestones[0].date
                  ? ` · ${state.fast.milestones[0].date}`
                  : " · no date set"}
              </p>
            </div>
          ) : null}
          {state.slow.blockers.length ? (
            <div>
              <span className={LABEL}>
                Open blockers
                {provenance.blockers === "inferred" ? <InferredBadge /> : null}
              </span>
              <ul className="list-disc pl-5">
                {state.slow.blockers.map((blocker) => (
                  <li key={blocker.id}>{blocker.text}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="text-[11.5px] text-[var(--text-muted)]">
            Judged against a {timeline.buffer_days}-day deadline buffer (
            {timeline.buffer_source}) and a {timeline.window_days}-day writing
            window ({timeline.window_source}).
          </p>
          {error ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
          {canEdit ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => open(state)}
                className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
              >
                Edit state
              </button>
              <button
                type="button"
                onClick={() => void confirm()}
                disabled={busy}
                className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt disabled:opacity-50"
              >
                {busy ? "Saving…" : "Still true"}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  );
}


/**
 * "Read from a document" — a file picker wearing a button.
 *
 * Offered wherever the questions are asked, because the usual honest answer to
 * "what does this project claim" is "it is in the proposal I already wrote".
 */
function DocumentButton({
  inputRef,
  reading,
  onPick,
}: {
  inputRef: React.RefObject<HTMLInputElement | null>;
  reading: boolean;
  onPick: (file: File) => void;
}) {
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.txt,.md,text/plain,application/pdf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onPick(file);
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={reading}
        className="rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt disabled:opacity-50"
      >
        {reading ? "Reading…" : "Read from a document"}
      </button>
    </>
  );
}
