"use client";

import { DevelopmentRow } from "@/components/portal/ambient/mylo-and-you-section";
import { Card } from "@/components/portal/primitives/card";
import { useProjectDevelopments } from "@/lib/portal/ambient/hooks";

/**
 * A project's developments, as conversation recorded them (ambient Plan 07,
 * step 13): data that arrived, a blocker that closed, a method dropped. Each
 * with its date and Mylo's account; a private one (said in a DM) only for the
 * person who said it. Absent when there is nothing to show, like the
 * reflection card above it. Undo lives on "Mylo & you".
 */
export function ProjectDevelopmentsCard({ projectId }: { projectId: string }) {
  const developments = useProjectDevelopments(projectId);
  const rows = developments.data?.developments ?? [];
  if (developments.isLoading || developments.isError || !rows.length) {
    return null;
  }
  return (
    <Card className="p-[18px]" aria-labelledby="project-developments-title">
      <h2
        id="project-developments-title"
        className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]"
      >
        Developments
      </h2>
      <ul className="mt-2 space-y-2">
        {rows.map((row) => (
          <DevelopmentRow key={row.id} row={row} />
        ))}
      </ul>
    </Card>
  );
}
