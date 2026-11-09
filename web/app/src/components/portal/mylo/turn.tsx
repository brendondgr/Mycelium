"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";

import { splitCitations, type Turn as TurnModel, type TurnStatus } from "@/lib/portal/agent/turns";
import type { AgentReference } from "@/lib/portal/agent/types";

import { ActivityFold } from "./activity-fold";
import { splitItemTitle } from "./open-ref";

/**
 * One turn: what the person asked, the activity fold, Mylo's answer with its
 * citations as small numbered pills, and — if it went wrong — the error in
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

      <ActivityFold turn={turn} status={status} announce={isLast} />

      {answer ? (
        <div className="ws-mylo-msg" data-from="mylo">
          <p className="ws-mylo-who">Mylo</p>
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

/**
 * Mylo's text: paragraphs and simple lists, `**bold**`, and `#n` citations as
 * pills. Built from React text nodes only — nothing the model writes is ever
 * read as HTML.
 */
export function AnswerText({
  text,
  references,
  onCite,
}: {
  text: string;
  references: AgentReference[];
  onCite: (ref: AgentReference) => void;
}) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="ws-mylo-answer">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        const bullets = lines.every((l) => /^\s*([-*•]|\d+[.)])\s+/.test(l));
        if (bullets) {
          const ordered = /^\s*\d/.test(lines[0]);
          const items = lines.map((l) => l.replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
          const List = ordered ? "ol" : "ul";
          return (
            <List key={i}>
              {items.map((item, j) => (
                <li key={j}>
                  <Inline text={item} references={references} onCite={onCite} />
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={i}>
            {lines.map((line, j) => (
              <React.Fragment key={j}>
                {j ? <br /> : null}
                <Inline text={line.replace(/^#{1,4}\s+/, "")} references={references} onCite={onCite} />
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function Inline({
  text,
  references,
  onCite,
}: {
  text: string;
  references: AgentReference[];
  onCite: (ref: AgentReference) => void;
}) {
  // Bold first, citations inside it: "**#16 — a call**" is one bold run that
  // holds a pill, not two stray pairs of asterisks around one.
  const runs = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {runs.map((run, i) => {
        const inner = <Cited text={run} references={references} onCite={onCite} />;
        return i % 2 ? <strong key={i}>{inner}</strong> : <React.Fragment key={i}>{inner}</React.Fragment>;
      })}
    </>
  );
}

function Cited({
  text,
  references,
  onCite,
}: {
  text: string;
  references: AgentReference[];
  onCite: (ref: AgentReference) => void;
}) {
  return (
    <>
      {splitCitations(text).map((part, i) => {
        if (!("cite" in part)) return <React.Fragment key={i}>{part.text}</React.Fragment>;
        const ref = references.find((r) => r.n === part.cite);
        if (!ref) return <React.Fragment key={i}>{`#${part.cite}`}</React.Fragment>;
        const title = splitItemTitle(ref.title).title;
        return (
          <button
            key={i}
            type="button"
            className="ws-mylo-cite"
            title={title}
            aria-label={`Source ${ref.n}: ${title}`}
            onClick={() => onCite(ref)}
          >
            {ref.n}
          </button>
        );
      })}
    </>
  );
}
