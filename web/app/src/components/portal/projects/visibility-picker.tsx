"use client";

import * as React from "react";

import type { ProjectVisibility } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Where a project lives, as the scope picker needs it to spell things out. */
export type ProjectHome =
  | { kind: "personal" }
  | { kind: "lab"; labName: string; departmentName: string | null }
  | { kind: "department"; departmentName: string };

export const VISIBILITY_LABEL: Record<ProjectVisibility, string> = {
  invite_only: "Invite only",
  lab: "Lab",
  department: "Department",
  public: "Everyone on this instance",
};

/** The scopes a project in `home` may take, narrowest first (mirrors the
 * backend's `visibility.allowed_visibilities`). */
export function allowedVisibilities(home: ProjectHome): ProjectVisibility[] {
  if (home.kind === "lab") {
    return home.departmentName
      ? ["invite_only", "lab", "department", "public"]
      : ["invite_only", "lab", "public"];
  }
  if (home.kind === "department") {
    return ["invite_only", "department", "public"];
  }
  return ["invite_only", "public"];
}

/**
 * What a scope means, in plain words: who sees the project exists, who can
 * still open it, and where Mylo may mention it. The product promises to say
 * these things plainly (plan "Things the product must say plainly"), so the
 * picker says them every time rather than in a help page.
 */
export function visibilityConsequence(
  value: ProjectVisibility,
  home: ProjectHome,
): string {
  const lab = home.kind === "lab" ? home.labName : "the lab";
  const dept =
    home.kind === "lab"
      ? home.departmentName
      : home.kind === "department"
        ? home.departmentName
        : null;
  switch (value) {
    case "invite_only":
      if (home.kind === "personal") {
        return "Only you and the people you invite. No lab or department can see it exists — this is the choice for a project nobody else may know about.";
      }
      if (home.kind === "lab") {
        return `Only the people you invite. This hides it from the other members of ${lab}, not from its PI: the lab's PI and admins can still open every lab project${
          dept ? `, and so can ${dept}'s heads unless the PI shows them names only` : ""
        }. Mylo mentions it only to its members, in their DMs and their own reports.`;
      }
      return `Only the people you invite, plus ${dept}'s owner and admins. Mylo mentions it only to its members.`;
    case "lab":
      return `Everyone in ${lab} sees that it exists — its name, one-line focus, owner and team size — and can ask to join. Mylo may mention it in ${lab}'s reports and in the lab's own Discord server, guests in that server included, but never in a department server.`;
    case "department":
      return `Everyone in ${dept ?? "the department"}${
        home.kind === "lab" ? ` and in ${lab}` : ""
      } sees that it exists and can ask to join. Mylo may mention it in the department's reports and servers.`;
    case "public":
      return "Any verified account on this Mycelium instance sees that it exists and can ask to join. It is never shown to anyone signed out.";
  }
}

/**
 * The scope picker: one radio per scope the project may take, each with what
 * it means. A request to join still needs the owner's or an editor's
 * approval, whatever the scope — the footnote says so.
 */
export function VisibilityPicker({
  value,
  onChange,
  home,
  allowed,
  disabled,
  name = "project-visibility",
}: {
  value: ProjectVisibility;
  onChange: (value: ProjectVisibility) => void;
  home: ProjectHome;
  allowed?: ProjectVisibility[];
  disabled?: boolean;
  name?: string;
}) {
  const options = allowed ?? allowedVisibilities(home);
  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="sr-only">Who can see this project</legend>
      {options.map((option) => {
        const id = `${name}-${option}`;
        const active = option === value;
        return (
          <label
            key={option}
            htmlFor={id}
            className={cn(
              "flex cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2.5 transition-colors",
              active
                ? "border-primary bg-surface-alt"
                : "border-border bg-surface hover:bg-surface-alt",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <input
              id={id}
              type="radio"
              name={name}
              value={option}
              checked={active}
              onChange={() => onChange(option)}
              className="mt-[3px] accent-[var(--primary)]"
            />
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold text-[var(--text-primary)]">
                {VISIBILITY_LABEL[option]}
              </span>
              <span className="mt-0.5 block text-[12px] leading-relaxed text-[var(--text-secondary)]">
                {visibilityConsequence(option, home)}
              </span>
            </span>
          </label>
        );
      })}
      <p className="text-[11.5px] leading-relaxed text-[var(--text-secondary)]">
        Seeing a project is not joining it: people join by your invitation or
        an approved request, and only members see its goals, feed and files.
      </p>
    </fieldset>
  );
}
