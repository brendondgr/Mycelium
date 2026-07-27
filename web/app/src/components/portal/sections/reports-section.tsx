"use client";

import * as React from "react";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { DocumentIcon } from "@/components/portal/icons";

export function ReportsSection() {
  return (
    <div>
      <SectionHeader
        eyebrow="From Mylo"
        title="Reports"
        subtitle="Shareable summaries of what changed across your labs."
      />
      <EmptyState
        icon={<DocumentIcon size={28} />}
        badge="Coming soon"
        title="Monthly research reports"
        description="Soon Mylo will compile monthly summaries of new papers, opportunity matches, and project progress — formatted to share with collaborators and department heads."
        action={
          <span
            className="rounded-full bg-surface-alt px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] cursor-not-allowed"
            aria-disabled="true"
          >
            Notify me when ready
          </span>
        }
      />
    </div>
  );
}
