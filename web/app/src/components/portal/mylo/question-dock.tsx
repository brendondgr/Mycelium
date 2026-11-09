"use client";

import type { TurnQuestion } from "@/lib/portal/agent/turns";

import { MyloHead } from "./mylo-head";

/**
 * Mylo is waiting on the person: its question, sitting just above the
 * composer, with the options it offered as buttons. The composer below is
 * the free-text answer.
 */
export function QuestionDock({
  question,
  onAnswer,
  busy,
}: {
  question: TurnQuestion;
  onAnswer: (text: string) => void;
  busy: boolean;
}) {
  return (
    <section className="ws-mylo-dock" aria-label="Mylo is asking you">
      <div className="ws-mylo-dock-q">
        <MyloHead size={20} />
        <p>{question.question || "Mylo has a question."}</p>
      </div>
      {question.options.length ? (
        <div className="ws-mylo-dock-options">
          {question.options.map((option) => (
            <button
              key={option}
              type="button"
              className="ws-mylo-chip"
              disabled={busy}
              onClick={() => onAnswer(option)}
            >
              {option}
            </button>
          ))}
        </div>
      ) : null}
      <p className="ws-mylo-dock-hint">Or type your answer below.</p>
    </section>
  );
}
