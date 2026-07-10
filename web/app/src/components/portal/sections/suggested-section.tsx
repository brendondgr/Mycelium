"use client";

import * as React from "react";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CloseIcon, SporeNode } from "@/components/portal/icons";
import { useDismissSuggestion, useMemberSuggestions } from "@/lib/portal/hooks";
import type { MemberSuggestion } from "@/lib/portal/types";

// ---------------------------------------------------------------------------
// Skeleton row — shown while suggestions are loading
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <div className="animate-pulse border-b border-[var(--divider)] px-5 py-[14px]">
      <div className="flex items-start justify-between gap-3">
        <span className="block h-3.5 w-2/3 rounded bg-surface-alt" />
        <span className="h-5 w-16 shrink-0 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-2.5 block h-2.5 w-1/3 rounded bg-surface-alt" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// SuggestedSection — "Suggested for you": papers teammates shared that
// closely match the caller's own research profile.
// ---------------------------------------------------------------------------

export function SuggestedSection() {
  const { data, isLoading, isError } = useMemberSuggestions();
  const suggestions = data?.items ?? [];

  return (
    <div>
      <SectionHeader
        title="Suggested for you"
        subtitle="Papers your teammates shared that closely match your own research profile."
      />

      {isLoading ? (
        <Card className="overflow-hidden">
          {[1, 2, 3].map((i) => (
            <SkeletonRow key={i} />
          ))}
        </Card>
      ) : isError ? (
        <p className="text-sm text-[var(--text-muted)]">
          Couldn&apos;t load your suggestions.
        </p>
      ) : suggestions.length === 0 ? (
        <EmptyState
          icon={<SporeNode size={26} />}
          title="Nothing suggested yet"
          description="When a teammate shares a paper that closely matches your research profile, it'll show up here."
        />
      ) : (
        <Card className="overflow-hidden">
          {suggestions.map((suggestion) => (
            <SuggestionListRow key={suggestion.id} suggestion={suggestion} />
          ))}
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One suggestion row: title → link, match %, project, who shared it, dismiss.
// ---------------------------------------------------------------------------

function SuggestionListRow({ suggestion }: { suggestion: MemberSuggestion }) {
  const dismiss = useDismissSuggestion();
  const [error, setError] = React.useState<string | null>(null);

  const handleDismiss = () => {
    setError(null);
    dismiss.mutate(suggestion.id, {
      onError: (e) => setError((e as Error).message),
    });
  };

  return (
    <div className="border-b border-[var(--divider)] px-5 py-[14px] last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        {suggestion.url ? (
          <a
            href={suggestion.url}
            target="_blank"
            rel="noreferrer"
            className="text-[14px] font-semibold leading-snug text-[var(--text-primary)] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {suggestion.title}
          </a>
        ) : (
          <span className="text-[14px] font-semibold leading-snug text-[var(--text-primary)]">
            {suggestion.title}
          </span>
        )}
        <div className="flex shrink-0 items-center gap-2">
          {suggestion.match_percent !== null ? (
            <span className="rounded-full bg-surface-alt px-2 py-[2px] text-[11px] font-semibold text-[var(--text-secondary)]">
              {suggestion.match_percent}% match
            </span>
          ) : null}
          <button
            type="button"
            onClick={handleDismiss}
            disabled={dismiss.isPending}
            aria-label={`Dismiss suggestion: ${suggestion.title}`}
            title="Dismiss"
            className="shrink-0 rounded-full p-1.5 text-[var(--text-muted)] transition-colors hover:bg-surface-alt hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <CloseIcon size={12} />
          </button>
        </div>
      </div>

      <p className="mt-1 text-[11.5px] uppercase tracking-wide text-[var(--text-muted)]">
        {suggestion.project.name}
      </p>

      {suggestion.shared_by ? (
        <div className="mt-2.5 flex items-center gap-2">
          <Avatar
            initials={suggestion.shared_by.initials}
            seed={suggestion.shared_by.username}
            size={20}
          />
          <span className="text-[12.5px] font-medium text-[var(--text-secondary)]">
            {suggestion.shared_by.name}
          </span>
          <span className="text-[11px] text-[var(--text-muted)]">shared this</span>
        </div>
      ) : null}

      {error ? (
        <p className="mt-2 text-[11px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
