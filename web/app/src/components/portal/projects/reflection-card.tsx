"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { useReflections } from "@/lib/portal/hooks";
import { decideReflection } from "@/lib/portal/mutations";
import type { ReflectionProposal } from "@/lib/portal/types";
import { useQueryClient } from "@tanstack/react-query";

/**
 * What Mylo noticed about how you actually worked, as questions you answer.
 *
 * These come from deterministic rules over what the reader saved, dismissed and
 * left undated — not from a model's opinion about their research. That
 * distinction is the whole design: accepting one edits the project's state, and
 * a machine writing into the document someone wrote about their own work is the
 * one thing the product must never do without being asked.
 *
 * So each card says plainly what prompted it — four saves sharing a word, six
 * dismissals sharing another — and each has exactly two buttons. Rejecting is a
 * real answer: a declined proposal is not raised again for four weeks.
 */

function summarise(row: ReflectionProposal): { title: string; why: string } {
  const evidence = row.evidence ?? {};
  const term = evidence.shared_term ? `“${evidence.shared_term}”` : "a topic";
  switch (row.kind) {
    case "add_method":
      return {
        title: `Add ${term} to ${row.project_name}'s method?`,
        why: `You saved ${evidence.saved ?? "several"} items sharing that term, and the project does not name it.`,
      };
    case "add_exclusion":
      return {
        title: `Stop surfacing ${term} for ${row.project_name}?`,
        why: `You dismissed ${evidence.dismissed ?? "several"} items sharing that term. Mylo has been getting this one wrong.`,
      };
    case "set_milestone":
      return {
        title: `Set a milestone date for ${row.project_name}?`,
        why: `Mylo could not judge ${(evidence.venues ?? []).join(", ") || "some venues"} because no milestone is dated.`,
      };
    default: {
      const days = evidence.days_since_confirmed;
      return {
        title: `Is ${row.project_name}'s state still right?`,
        why:
          days == null
            ? "Nobody has confirmed it yet, and the reports read it as current."
            : `It was last confirmed ${days} days ago, and the reports read it as current.`,
      };
    }
  }
}

export function ReflectionCard() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useReflections();
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function decide(row: ReflectionProposal, action: "accept" | "reject") {
    if (busy) return;
    setBusy(row.id);
    setError(null);
    try {
      await decideReflection(row.id, action);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portal", "reflections"] }),
        queryClient.invalidateQueries({
          queryKey: ["portal", "project-state", row.project_id],
        }),
      ]);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save that. Try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  // Absent rather than empty: a card headed "Mylo's reflection" with nothing
  // under it implies Mylo failed to think of anything, which is not what a week
  // with no pattern in it means.
  if (isLoading || !data?.length) return null;

  return (
    <Card className="p-5">
      <h2 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Mylo&rsquo;s reflection
      </h2>
      <p className="mb-3 text-[12.5px] leading-5 text-[var(--text-secondary)]">
        Drawn from what you saved and dismissed, not from an opinion about your
        research. Nothing changes until you say so.
      </p>

      <ul className="divide-y divide-[var(--divider)]">
        {data.map((row) => {
          const { title, why } = summarise(row);
          return (
            <li key={row.id} className="py-3 first:pt-0 last:pb-0">
              <p className="text-[13.5px] font-semibold text-[var(--text-primary)]">
                {title}
              </p>
              <p className="mt-0.5 text-[12.5px] leading-5 text-[var(--text-secondary)]">
                {why}
              </p>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy === row.id}
                  onClick={() => void decide(row, "accept")}
                  className="rounded-full bg-primary px-3.5 py-1.5 text-[12.5px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                >
                  {row.kind === "review_state" ? "Still right" : "Accept"}
                </button>
                <button
                  type="button"
                  disabled={busy === row.id}
                  onClick={() => void decide(row, "reject")}
                  className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[12.5px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt disabled:opacity-50"
                >
                  {row.kind === "review_state" ? "Needs updating" : "No thanks"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      {error ? (
        <p className="mt-3 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
