"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import {
  useSetDepartmentProjectCreation,
  useSetLabProjectCreation,
} from "@/lib/portal/hooks";
import type { ProjectCreation } from "@/lib/portal/types";

const OPTIONS: { value: ProjectCreation; label: string; hint: string }[] = [
  {
    value: "members",
    label: "Any member",
    hint: "Anyone in it can start a project and owns what they start. Viewers cannot.",
  },
  {
    value: "managers",
    label: "Managers only",
    hint: "Only the PI, owner and admins start projects.",
  },
];

/**
 * *Who can create projects* for a lab or a department. Whoever starts a
 * project owns it; the active-project limit stays the lab's (or the
 * department's) either way.
 */
export function ProjectCreationCard(
  props:
    | { kind: "lab"; slug: string; value: ProjectCreation }
    | { kind: "department"; id: string; value: ProjectCreation },
) {
  const lab = useSetLabProjectCreation(props.kind === "lab" ? props.slug : "");
  const department = useSetDepartmentProjectCreation(
    props.kind === "department" ? props.id : "",
  );
  const save = props.kind === "lab" ? lab : department;
  const [error, setError] = React.useState<string | null>(null);
  const name = `project-creation-${props.kind === "lab" ? props.slug : props.id}`;

  return (
    <Card className="p-5">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Who can create projects
      </h3>
      <p className="mb-3 text-[12.5px] text-[var(--text-secondary)]">
        Whoever starts a project owns it. Every project still counts against
        this {props.kind}&apos;s project limit.
      </p>
      <fieldset className="space-y-2" disabled={save.isPending}>
        <legend className="sr-only">Who can create projects</legend>
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 has-[:checked]:border-primary"
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={props.value === option.value}
              onChange={() => {
                setError(null);
                save.mutate(option.value, {
                  onError: (e) => setError((e as Error).message),
                });
              }}
              className="mt-[3px] h-4 w-4 shrink-0 accent-[var(--primary)]"
            />
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold">
                {option.label}
              </span>
              <span className="block text-[12px] text-[var(--text-secondary)]">
                {option.hint}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
      {error ? (
        <p className="mt-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
