"use client";

import * as React from "react";
import { Check, ChevronRight, X } from "lucide-react";

import {
  currentActivity,
  foldSummary,
  type Turn,
  type TurnStatus,
} from "@/lib/portal/agent/turns";

import type { AgentReference } from "@/lib/portal/agent/types";

import { MyloHead } from "./mylo-head";
import { refHref, splitItemTitle } from "./open-ref";

/**
 * Mylo's row in a turn — face, name, and what Mylo is doing, never what it
 * is thinking (S-9). The row stays for every answer, so the face does not
 * come and go; a turn that took no steps shows just the face and the name.
 *
 * While Mylo works the header names the current step with a quiet shimmer
 * ("Searching the corpus for …"). Opened, it lists the steps taken with a
 * tick or a cross; a step that read one of the thread's sources opens it.
 * Once the turn ends it collapses to "Looked at 3 things".
 * Every label is the server's; the fold has no words of its own for a step.
 */
export function ActivityFold({
  turn,
  status,
  announce,
  hasAnswer,
  references,
  onOpen,
}: {
  turn: Turn;
  status: TurnStatus;
  /** The last turn's fold is a polite live region; older ones are not. */
  announce: boolean;
  hasAnswer: boolean;
  references: AgentReference[];
  /** Open the thing a step looked at. */
  onOpen: (ref: AgentReference) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const id = React.useId();
  const working = status === "working";
  const steps = turn.steps;
  if (!working && !steps.length && !hasAnswer) return null;

  const now = working ? `${currentActivity(turn)}…` : foldSummary(steps);
  return (
    <div className="ws-mylo-fold" data-working={working || undefined}>
      <div className="ws-mylo-fold-row">
        <MyloHead size={22} working={working} />
        <span className="ws-mylo-who">Mylo</span>
        {!now ? null : steps.length ? (
          <button
            type="button"
            className="ws-mylo-fold-head"
            aria-expanded={open}
            aria-controls={id}
            onClick={() => setOpen((o) => !o)}
          >
            <span className={working ? "ws-mylo-shimmer" : undefined}>{now}</span>
            <ChevronRight size={13} aria-hidden="true" className="ws-mylo-chev" />
          </button>
        ) : (
          <span className="ws-mylo-fold-head ws-mylo-fold-static">
            <span className="ws-mylo-shimmer">{now}</span>
          </span>
        )}
      </div>
      {announce ? (
        // Announces a step once: the text changes per step, not per token.
        <span className="ws-sr" role="status" aria-live="polite">
          {working ? currentActivity(turn) : steps.length ? now : ""}
        </span>
      ) : null}
      {open && steps.length ? (
        <ol id={id} className="ws-mylo-steps" aria-label="Steps Mylo took">
          {steps.map((step) => (
            <li key={step.callId} data-state={step.state}>
              {step.state === "ok" ? (
                <Check size={13} aria-hidden="true" />
              ) : step.state === "failed" ? (
                <X size={13} aria-hidden="true" />
              ) : (
                <span className="ws-mylo-dot" aria-hidden="true" />
              )}
              <StepLabel step={step} references={references} onOpen={onOpen} />
              <span className="ws-sr">
                {step.state === "ok" ? " (done)" : step.state === "failed" ? " (didn’t work)" : " (in progress)"}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

/** A step's words; a button when the step read something that can be opened. */
function StepLabel({
  step,
  references,
  onOpen,
}: {
  step: Turn["steps"][number];
  references: AgentReference[];
  onOpen: (ref: AgentReference) => void;
}) {
  const ref = step.ref === null ? undefined : references.find((r) => r.n === step.ref);
  if (!ref || !refHref(ref)) return <span>{step.label}</span>;
  return (
    <button
      type="button"
      className="ws-mylo-step-link"
      title={`Open “${splitItemTitle(ref.title).title}”`}
      onClick={() => onOpen(ref)}
    >
      {step.label}
    </button>
  );
}
