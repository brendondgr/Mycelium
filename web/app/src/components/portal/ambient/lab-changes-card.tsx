"use client";

import { Card } from "@/components/portal/primitives/card";
import { useLabChanges } from "@/lib/portal/ambient/hooks";

/**
 * A lab's "What changed" (ambient Plan 07, step 7): the lab's shared projects
 * only — developments recorded or confirmed, with who confirmed them. The API
 * returns nothing personal to a lab, whoever asks; this card only renders it.
 */
export function LabChangesCard({ slug }: { slug: string }) {
  const changes = useLabChanges(slug);
  const rows = changes.data?.changes ?? [];
  if (changes.isLoading || changes.isError || !rows.length) {
    return null;
  }
  return (
    <Card className="p-[18px]" aria-labelledby="lab-changes-title" data-ambient="lab-changes">
      <h2
        id="lab-changes-title"
        className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]"
      >
        What changed in the lab&apos;s projects
      </h2>
      <ul className="mt-2 divide-y divide-[var(--divider)]">
        {rows.slice(0, 12).map((row) => (
          <li key={row.id} className="py-2 text-sm">
            <p className="text-[var(--text-primary)]">
              {row.topic}
              {row.project ? (
                <span className="text-[var(--text-muted)]"> · {row.project.name}</span>
              ) : null}
            </p>
            <p className="text-[12px] text-[var(--text-muted)]">
              {row.kind_label} ·{" "}
              {new Date(row.created_at).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })}{" "}
              · {row.by.you ? "you" : row.by.name}
              {row.undone_at ? " · undone" : ""}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
