"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { useSetLabDepartmentSees } from "@/lib/portal/hooks";
import type { DepartmentSees, MyLab } from "@/lib/portal/types";

const DEPARTMENT_SEES_OPTIONS: {
  value: DepartmentSees;
  label: string;
  hint: string;
}[] = [
  {
    value: "everything",
    label: "Everything",
    hint: "The department's heads can open every project in this lab.",
  },
  {
    value: "names_only",
    label: "Names only",
    hint: "They see each project's name, owner, member count and scope — not its goals, feed, files or team.",
  },
];

/** What the lab's department heads see of its projects. Set here, by the lab's
 * PI / owner / admin — never by the department. A project the head is a
 * member of opens in full either way. */
export function DepartmentSeesCard({ lab }: { lab: MyLab }) {
  const save = useSetLabDepartmentSees(lab.slug);
  const [error, setError] = React.useState<string | null>(null);

  return (
    <Card className="p-5">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        What {lab.department} sees
      </h3>
      <p className="mb-3 text-[12.5px] text-[var(--text-secondary)]">
        Of this lab&apos;s projects, for the department&apos;s heads. A
        project they are a member of always opens in full.
      </p>
      <fieldset className="space-y-2" disabled={save.isPending}>
        <legend className="sr-only">What the department sees</legend>
        {DEPARTMENT_SEES_OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 has-[:checked]:border-primary"
          >
            <input
              type="radio"
              name={`department-sees-${lab.slug}`}
              value={option.value}
              checked={lab.department_sees === option.value}
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
