"use client";

import * as React from "react";
import { Check, ChevronRight, X } from "lucide-react";

import {
  currentActivity,
  foldSummary,
  type Turn,
  type TurnStatus,
} from "@/lib/portal/agent/turns";

import { MyloHead } from "./mylo-head";

/**
 * One fold per turn: what Mylo is doing, never what it is thinking (S-9).
 *
 * While Mylo works the header names the current step with a quiet shimmer
 * ("Searching the corpus for …"). Opened, it lists the steps taken with a
 * tick or a cross. Once the turn ends it collapses to "Looked at 3 things".
 * Every label is the server's; the fold has no words of its own for a step.
 */
export function ActivityFold({
  turn,
  status,
  announce,
}: {
  turn: Turn;
  status: TurnStatus;
  /** The last turn's fold is a polite live region; older ones are not. */
  announce: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const id = React.useId();
  const working = status === "working";
  const steps = turn.steps;
  if (!working && !steps.length) return null;

  const now = working ? `${currentActivity(turn)}…` : foldSummary(steps);
  return (
    <div className="ws-mylo-fold" data-working={working || undefined}>
      <div className="ws-mylo-fold-row">
        <MyloHead size={22} working={working} />
        {steps.length ? (
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
              <span>{step.label}</span>
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
