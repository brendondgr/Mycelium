"use client";

import * as React from "react";

import { usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { ConfirmModal } from "@/components/portal/sections/member-row";
import {
  useProjectOwnership,
  useProjectOwnershipActions,
} from "@/lib/portal/hooks";
import type { Project } from "@/lib/portal/types";

const BUTTON =
  "rounded-full border border-[var(--divider)] px-4 py-2 text-xs font-semibold " +
  "text-[var(--text-primary)] transition-colors hover:border-primary " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
  "disabled:opacity-50";

type Pending =
  | { kind: "hand"; username: string; name: string }
  | { kind: "take" }
  | { kind: "offer" }
  | { kind: "withdraw" }
  | { kind: "accept" };

/**
 * Who owns a lab or department project, and the three things that can change
 * it: the owner hands it to someone on the project, the lab's (or
 * department's) managers take it, and the owner offers a lab project to the
 * lab's department, whose head accepts. Renders nothing for a personal
 * project or for someone who can do none of these.
 */
export function ProjectOwnershipCard({ project }: { project: Project }) {
  const { user } = usePortal();
  const state = useProjectOwnership(project.id);
  const actions = useProjectOwnershipActions(project.id);
  const [pending, setPending] = React.useState<Pending | null>(null);
  const [choice, setChoice] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const data = state.data;
  if (project.scope === "user" || !data) return null;
  const transfer = data.transfer;
  const anything =
    data.can_hand_over ||
    data.can_take ||
    data.can_offer ||
    Boolean(transfer && (transfer.can_accept || transfer.can_withdraw));
  if (!anything) return null;

  const owner = project.members.find((m) => m.role === "owner") ?? null;
  // Ownership goes to someone already on the project, and not to its owner.
  const candidates = project.members.filter(
    (m) => m.role !== "owner" && m.username !== user.username,
  );
  const selected = candidates.find((m) => m.username === choice) ?? null;
  const busy =
    actions.setOwner.isPending ||
    actions.offer.isPending ||
    actions.withdraw.isPending ||
    actions.accept.isPending;

  const done = {
    onSuccess: () => {
      setPending(null);
      setChoice("");
    },
    onError: (e: unknown) => {
      setPending(null);
      setError((e as Error).message);
    },
  };

  const confirm = () => {
    if (!pending) return;
    setError(null);
    if (pending.kind === "hand") actions.setOwner.mutate(pending.username, done);
    else if (pending.kind === "take") actions.setOwner.mutate(user.username, done);
    else if (pending.kind === "offer") actions.offer.mutate(undefined, done);
    else if (pending.kind === "withdraw") actions.withdraw.mutate(undefined, done);
    else actions.accept.mutate(undefined, done);
  };

  const dialog = (() => {
    if (!pending) return null;
    switch (pending.kind) {
      case "hand":
        return {
          title: `Hand ${project.name} to ${pending.name}?`,
          body: `${pending.name} becomes the owner and decides who sees the project. You stay on it as an editor. Everyone on the project is told.`,
          confirmLabel: "Hand over",
        };
      case "take":
        return {
          title: `Take ${project.name}?`,
          body: `You become the owner${owner ? ` and ${owner.name} becomes an editor` : ""}. Everyone on the project is told, and it is recorded.`,
          confirmLabel: "Take ownership",
        };
      case "offer":
        return {
          title: `Offer ${project.name} to ${data.department}?`,
          body: `If a head of ${data.department} accepts, the project becomes the department's and keeps its members. A project seen by the whole lab becomes invite-only there. You can withdraw the offer until it is accepted.`,
          confirmLabel: "Offer it",
        };
      case "withdraw":
        return {
          title: "Withdraw the offer?",
          body: `${project.name} stays with ${project.scope_name}.`,
          confirmLabel: "Withdraw",
        };
      default:
        return {
          title: `Take ${project.name} into ${transfer?.department ?? "the department"}?`,
          body: `The project becomes the department's and keeps its members. It no longer belongs to ${project.scope_name}. This cannot be undone from here.`,
          confirmLabel: "Accept",
        };
    }
  })();

  return (
    <Card className="p-5" aria-labelledby="project-ownership-title">
      <h3
        id="project-ownership-title"
        className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]"
      >
        Ownership
      </h3>
      <p className="mb-3 text-[12.5px] text-[var(--text-secondary)]">
        {owner ? `${owner.name} owns this project.` : "This project has no owner."}{" "}
        The owner decides who sees it.
      </p>

      <div className="flex flex-col gap-4">
        {data.can_hand_over ? (
          <div>
            <label
              htmlFor="project-new-owner"
              className="mb-1 block text-[12.5px] font-semibold text-[var(--text-primary)]"
            >
              Hand it to someone on the project
            </label>
            {candidates.length ? (
              <div className="flex flex-wrap items-center gap-2">
                <select
                  id="project-new-owner"
                  value={choice}
                  onChange={(e) => setChoice(e.target.value)}
                  disabled={busy}
                  className="min-w-0 flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-[13px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">Choose a person</option>
                  {candidates.map((m) => (
                    <option key={m.username} value={m.username}>
                      {m.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className={BUTTON}
                  disabled={busy || !selected}
                  onClick={() =>
                    selected &&
                    setPending({
                      kind: "hand",
                      username: selected.username,
                      name: selected.name,
                    })
                  }
                >
                  Hand over
                </button>
              </div>
            ) : (
              <p className="m-0 text-[12.5px] text-[var(--text-secondary)]">
                Nobody else is on the project yet. Invite someone first.
              </p>
            )}
          </div>
        ) : null}

        {data.can_take ? (
          <div>
            <p className="mb-2 text-[12.5px] text-[var(--text-secondary)]">
              As a manager of {project.scope_name} you can take this project
              yourself.
            </p>
            <button
              type="button"
              className={BUTTON}
              disabled={busy}
              onClick={() => setPending({ kind: "take" })}
            >
              Take ownership
            </button>
          </div>
        ) : null}

        {transfer ? (
          <div>
            <p className="mb-2 text-[12.5px] text-[var(--text-secondary)]">
              This project has been offered to {transfer.department}. It moves
              when a head of the department accepts.
            </p>
            <div className="flex flex-wrap gap-2">
              {transfer.can_accept ? (
                <button
                  type="button"
                  className={BUTTON}
                  disabled={busy}
                  onClick={() => setPending({ kind: "accept" })}
                >
                  Accept into {transfer.department}
                </button>
              ) : null}
              {transfer.can_withdraw ? (
                <button
                  type="button"
                  className={BUTTON}
                  disabled={busy}
                  onClick={() => setPending({ kind: "withdraw" })}
                >
                  Withdraw the offer
                </button>
              ) : null}
            </div>
          </div>
        ) : data.can_offer && data.department ? (
          <div>
            <p className="mb-2 text-[12.5px] text-[var(--text-secondary)]">
              Move this project from {project.scope_name} to {data.department},
              for example before the lab leaves the department.
            </p>
            <button
              type="button"
              className={BUTTON}
              disabled={busy}
              onClick={() => setPending({ kind: "offer" })}
            >
              Offer to {data.department}
            </button>
          </div>
        ) : null}
      </div>

      {error ? (
        <p className="mt-3 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}

      {pending && dialog ? (
        <ConfirmModal
          title={dialog.title}
          body={dialog.body}
          confirmLabel={dialog.confirmLabel}
          busy={busy}
          onClose={() => setPending(null)}
          onConfirm={confirm}
        />
      ) : null}
    </Card>
  );
}
