"use client";

import * as React from "react";

import { sendSlotFeedback } from "@/lib/portal/collab/client";
import type {
  SlotFeedbackKind,
  TeamFit,
  TeamFitSlot,
} from "@/lib/portal/collab/types";

const FACET_LABEL: Record<TeamFitSlot["facet"], string> = {
  problem: "Problem",
  method: "Method",
  data: "Data",
  role: "Partner",
};

/**
 * "You cover 2 of 3 · Gap: environmental health" — what a funding call asks a
 * team to bring, and which of it the reader (or their lab) already has.
 *
 * Collaboration-network plan CN-03. Deterministic: nothing here is Mylo's
 * opinion, it is the call's own requirements set against what people's
 * profiles state. A lab card names who covers each requirement, on the strength
 * of their stated profile only; a reader's own card counts their papers and the
 * suggestions they confirmed too, because it is theirs.
 *
 * A **partner** requirement ("a local authority as a partner") is shown and
 * never matched — no profile can supply one. Nothing renders when the call asks
 * for nothing: silence in a call means no requirement, not an unknown one.
 *
 * Every slot can be corrected ("not a requirement", "we do cover this", "you
 * missed one"); those corrections are how the requirement reader is measured.
 */
export function TeamFitLine({
  contentId,
  fit,
  forLab = false,
  className,
}: {
  contentId: string;
  fit: TeamFit | null | undefined;
  forLab?: boolean;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const detailsId = React.useId();

  if (!fit || (fit.total === 0 && fit.roles.length === 0)) return null;

  const who = forLab ? "Your lab covers" : "You cover";
  return (
    <div
      className={`mt-3 rounded-xl border border-border bg-surface-alt/60 px-3 py-2.5 ${className ?? ""}`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] leading-snug">
        <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
          Team fit
        </span>
        {fit.total > 0 ? (
          <span className="font-medium text-[var(--text-primary)]">
            {who} {fit.covered} of {fit.total}
          </span>
        ) : null}
        {fit.gaps.length > 0 ? (
          <span className="text-[var(--text-secondary)]">
            · Gap: {fit.gaps.join(", ")}
          </span>
        ) : null}
        {fit.roles.length > 0 ? (
          <span className="text-[var(--text-secondary)]">
            · Needs a partner: {fit.roles.join(", ")}
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={detailsId}
          className="ml-auto rounded-md px-1.5 py-0.5 text-xs font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {open ? "Hide" : "Details"}
        </button>
      </div>
      {open ? (
        <TeamFitDetails id={detailsId} contentId={contentId} fit={fit} />
      ) : null}
    </div>
  );
}

function TeamFitDetails({
  id,
  contentId,
  fit,
}: {
  id: string;
  contentId: string;
  fit: TeamFit;
}) {
  const [sent, setSent] = React.useState<Record<string, SlotFeedbackKind>>({});
  const [missed, setMissed] = React.useState("");
  const [problem, setProblem] = React.useState<string | null>(null);

  const send = async (
    key: string,
    body: { kind: SlotFeedbackKind; slot_text?: string; note?: string },
  ) => {
    setProblem(null);
    try {
      await sendSlotFeedback(contentId, body);
      setSent((current) => ({ ...current, [key]: body.kind }));
    } catch (error) {
      setProblem((error as Error).message);
    }
  };

  return (
    <div id={id} className="mt-2.5 border-t border-border pt-2.5">
      <ul className="space-y-2" aria-label="What this call asks a team to bring">
        {fit.slots.map((slot) => (
          <li
            key={`${slot.facet}:${slot.text}`}
            className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]"
          >
            <span className="rounded-full border border-border px-1.5 py-px text-[10.5px] font-semibold uppercase tracking-[0.04em] text-[var(--text-muted)]">
              {FACET_LABEL[slot.facet]}
            </span>
            <span className="text-[var(--text-primary)]">{slot.text}</span>
            {slot.required ? (
              <span className="text-[11px] font-medium text-clay">required</span>
            ) : null}
            <span className="text-[12px] text-[var(--text-secondary)]">
              {coverageNote(slot)}
            </span>
            <span className="ml-auto flex gap-1">
              {sent[slot.text] ? (
                <span className="text-[11.5px] text-[var(--text-muted)]">Noted, thank you</span>
              ) : (
                <>
                  <FeedbackButton
                    label="Not a requirement"
                    onClick={() =>
                      send(slot.text, { kind: "not_a_requirement", slot_text: slot.text })
                    }
                  />
                  {slot.facet !== "role" && slot.covered_by === null ? (
                    <FeedbackButton
                      label="We cover this"
                      onClick={() =>
                        send(slot.text, { kind: "we_cover_this", slot_text: slot.text })
                      }
                    />
                  ) : null}
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
      <form
        className="mt-2.5 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const note = missed.trim();
          if (note) {
            void send("__missed__", { kind: "missed_one", note }).then(() => setMissed(""));
          }
        }}
      >
        <label htmlFor={`${id}-missed`} className="text-[12px] text-[var(--text-secondary)]">
          Missed one?
        </label>
        <input
          id={`${id}-missed`}
          value={missed}
          onChange={(event) => setMissed(event.target.value)}
          maxLength={300}
          placeholder="What else does the call ask for"
          className="min-w-[12rem] flex-1 rounded-lg border border-border bg-surface px-2.5 py-1 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <button
          type="submit"
          disabled={!missed.trim()}
          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Send
        </button>
        {sent.__missed__ ? (
          <span className="text-[11.5px] text-[var(--text-muted)]">Noted, thank you</span>
        ) : null}
      </form>
      {problem ? (
        <p role="alert" className="mt-1.5 text-[12px] text-clay">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

function coverageNote(slot: TeamFitSlot): string {
  if (slot.facet === "role") return "a partner, not expertise";
  if (slot.covered_by === "you") {
    return slot.matched ? `you — ${slot.matched}` : "you";
  }
  if (slot.covered_by === "lab") {
    const names = slot.people.map((person) => person.name).join(", ");
    return names ? `covered by ${names}` : "covered in your lab";
  }
  return "a gap";
}

function FeedbackButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-border px-1.5 py-0.5 text-[11px] text-[var(--text-secondary)] hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
    </button>
  );
}
