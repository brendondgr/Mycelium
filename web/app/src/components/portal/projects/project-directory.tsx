"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { VISIBILITY_LABEL } from "@/components/portal/projects/visibility-picker";
import { useJoinRequests, useProjectDirectory } from "@/lib/portal/hooks";
import type { ProjectDirectoryRow } from "@/lib/portal/types";

const GHOST =
  "shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/**
 * The directory: projects the reader can see exist but is not on — "Projects
 * in this lab", "…in this department", or, from the personal workspace, every
 * project open to the whole instance.
 *
 * A row is deliberately thin: name, one-line focus, owner, team size and
 * scope. Goals, state, feed, files and the roster stay with the members. A
 * reader asks to join; an overseer (the lab's PI, a department head) may open
 * the project without joining, and it still is not one of their projects.
 */
export function ProjectDirectory({
  title,
  where,
  onOpen,
}: {
  title: string;
  where: { labSlug?: string; departmentId?: string };
  onOpen: (id: string) => void;
}) {
  const { data, isLoading, isError } = useProjectDirectory(where);
  const rows = data?.items ?? [];

  return (
    <section aria-labelledby="project-directory-title" className="mt-8">
      <h2
        id="project-directory-title"
        className="mb-1 text-[15px] font-semibold text-[var(--text-primary)]"
      >
        {title}
      </h2>
      <p className="mb-3 text-[12.5px] text-[var(--text-secondary)]">
        Projects you can see but are not on. Ask to join one; its owner or an
        editor decides.
      </p>
      {isLoading ? (
        <Card className="p-5">
          <div className="h-10 animate-pulse rounded-xl bg-surface-alt" />
        </Card>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load the directory.
        </p>
      ) : rows.length === 0 ? (
        <p className="text-[12.5px] text-[var(--text-secondary)]">
          Nothing here yet. Projects show up when their owner opens them to
          this group.
        </p>
      ) : (
        <Card className="overflow-hidden">
          {rows.map((row) => (
            <DirectoryRow key={row.id} row={row} onOpen={() => onOpen(row.id)} />
          ))}
        </Card>
      )}
    </section>
  );
}

function DirectoryRow({
  row,
  onOpen,
}: {
  row: ProjectDirectoryRow;
  onOpen: () => void;
}) {
  const { request } = useJoinRequests();
  const [error, setError] = React.useState<string | null>(null);

  return (
    <div className="flex flex-wrap items-center gap-x-[14px] gap-y-2 border-b border-[var(--divider)] px-5 py-4 last:border-b-0">
      <div className="min-w-0 flex-1 basis-[220px]">
        <p className="m-0 flex flex-wrap items-center gap-1.5 text-sm font-medium text-[var(--text-primary)]">
          <span className="truncate">{row.name}</span>
          <Pill tone="neutral" className="shrink-0">
            {VISIBILITY_LABEL[row.visibility]}
          </Pill>
        </p>
        {row.focus ? (
          <p className="m-0 mt-0.5 line-clamp-1 text-[12px] text-[var(--text-secondary)]">
            {row.focus}
          </p>
        ) : null}
        <p className="m-0 mt-0.5 text-[11.5px] text-[var(--text-secondary)]">
          {row.owner ? `Owner ${row.owner.name} · ` : ""}
          {row.member_count} member{row.member_count === 1 ? "" : "s"}
          {row.scope_name ? ` · ${row.scope_name}` : ""}
        </p>
        {error ? (
          <p className="m-0 mt-1 text-[11px] text-clay" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {row.can_open ? (
          <button type="button" onClick={onOpen} className={GHOST}>
            Open
          </button>
        ) : null}
        {row.request_status === "pending" ? (
          <Pill tone="dashed">Requested</Pill>
        ) : row.can_request ? (
          <button
            type="button"
            onClick={() => {
              setError(null);
              request.mutate(
                { id: row.id },
                { onError: (e) => setError((e as Error).message) },
              );
            }}
            disabled={request.isPending}
            className={GHOST}
          >
            {request.isPending ? "Asking…" : "Ask to join"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
