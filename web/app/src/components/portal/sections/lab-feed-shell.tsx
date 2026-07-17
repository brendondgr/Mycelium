"use client";

import * as React from "react";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";

/**
 * Shared chrome for a lab-scoped feed page (Research Papers / Grants /
 * Fellowships / Conferences when a lab is the active workspace). Pure layout — it
 * imports no card components, so the individual feed sections can compose it
 * without an import cycle. Each section reads the lab's combined recommendations
 * and renders its own area's items into `children`.
 */
export function LabFeedShell({
  title,
  subtitle,
  isLoading,
  isError,
  isEmpty,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  children,
}: {
  title: string;
  subtitle: React.ReactNode;
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyIcon: React.ReactNode;
  emptyTitle: string;
  emptyDescription: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <SectionHeader title={title} subtitle={subtitle} />
      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-28 animate-pulse rounded-2xl bg-surface-alt"
            />
          ))}
        </div>
      ) : isError ? (
        <EmptyState
          icon={emptyIcon}
          title="Couldn't load this feed"
          description="Something went wrong loading the lab's matches. Please try again in a moment."
        />
      ) : isEmpty ? (
        <EmptyState
          icon={emptyIcon}
          title={emptyTitle}
          description={emptyDescription}
        />
      ) : (
        children
      )}
    </div>
  );
}
