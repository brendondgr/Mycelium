"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";

import type { Turn as TurnModel, TurnStatus } from "@/lib/portal/agent/turns";
import type { AgentReference } from "@/lib/portal/agent/types";

import { ActivityFold } from "./activity-fold";
import { AnswerText } from "./answer";

/**
 * One turn: what the person asked, Mylo's row (face, name, what it looked
 * at), the answer with its citations as small numbered pills, and — if it went wrong — the error in
 * plain words with "Try again". No scores, percentages or verdicts.
 */
export function Turn({
  turn,
  status,
  isLast,
  references,
  onCite,
  onRetry,
}: {
  turn: TurnModel;
  status: TurnStatus;
  isLast: boolean;
  references: AgentReference[];
  onCite: (ref: AgentReference) => void;
  onRetry: (text: string) => void;
}) {
  const answer = turn.answer?.text || turn.draft;
  return (
    <li className="ws-mylo-turn">
      {turn.user ? (
        <div className="ws-mylo-msg" data-from="you">
          <p className="ws-mylo-who">You</p>
          <p className="ws-mylo-you">{turn.user.text}</p>
        </div>
      ) : null}

      <ActivityFold
        turn={turn}
        status={status}
        announce={isLast}
        hasAnswer={Boolean(answer)}
        references={references}
        onOpen={onCite}
      />

      {answer ? (
        <div className="ws-mylo-msg" data-from="mylo">
          <AnswerText text={answer} references={references} onCite={onCite} />
          {turn.answer?.partial || turn.stopped ? (
            <p className="ws-mylo-aside">Stopped before finishing.</p>
          ) : null}
        </div>
      ) : turn.stopped ? (
        <p className="ws-mylo-aside">Stopped.</p>
      ) : null}

      {turn.notes.map((note, i) => (
        <p key={i} className="ws-mylo-aside">
          {note}
        </p>
      ))}

      {turn.errors.map((error, i) => (
        <div key={i} className="ws-mylo-error" role="alert">
          <AlertCircle size={15} aria-hidden="true" />
          <div>
            <p>{error.detail}</p>
            {error.fix ? <p className="ws-mylo-fix">{error.fix}</p> : null}
            {turn.user && isLast ? (
              <button
                type="button"
                className="ws-mylo-link-btn"
                onClick={() => onRetry(turn.user!.text)}
              >
                Try again
              </button>
            ) : null}
          </div>
        </div>
      ))}
    </li>
  );
}
