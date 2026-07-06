"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ArrowRightIcon,
  CalendarIcon,
  ConferenceIcon,
} from "@/components/portal/icons";
import {
  MatchBadge,
  NewTag,
  SaveButton,
  deadlineLabel,
} from "@/components/portal/sections/opportunity-bits";
import { useConferences } from "@/lib/portal/hooks";
import type { ConferenceOpportunity } from "@/lib/portal/types";

function ConferenceCard({ conf }: { conf: ConferenceOpportunity }) {
  const where = conf.location || conf.country;
  // Use the semicolon-delimited subject categories, not the space-joined
  // `keywords` blob, so the tags render as real, separate chips.
  const subjects = conf.matched_subjects
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
  const shownSubjects = subjects.slice(0, 4);
  const moreSubjects = subjects.length - shownSubjects.length;

  return (
    <Card className="flex h-full flex-col p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {conf.is_new ? <NewTag /> : null}
          <MatchBadge percent={conf.match_percent} />
        </div>
        <SaveButton contentId={conf.content_id} saved={conf.saved} />
      </div>

      <h3 className="mt-2.5 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
        {conf.title}
      </h3>

      <dl className="mt-2.5 space-y-1.5 text-sm text-[var(--text-secondary)]">
        {where ? (
          <div className="flex gap-2">
            <dt className="w-12 shrink-0 font-medium text-[var(--text-muted)]">
              Where
            </dt>
            <dd className="min-w-0">{where}</dd>
          </div>
        ) : null}
        {conf.event_dates ? (
          <div className="flex gap-2">
            <dt className="w-12 shrink-0 font-medium text-[var(--text-muted)]">
              When
            </dt>
            <dd>{conf.event_dates}</dd>
          </div>
        ) : null}
      </dl>

      {conf.deadline_date ? (
        <p className="mt-2.5 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--destructive)]">
          <CalendarIcon size={15} aria-hidden="true" />
          {deadlineLabel(conf.deadline_kind, conf.deadline_date)}
        </p>
      ) : null}

      {conf.reason ? (
        <p className="mt-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
          {conf.reason}
        </p>
      ) : null}

      {shownSubjects.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {shownSubjects.map((subject) => (
            <span
              key={subject}
              className="rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              {subject}
            </span>
          ))}
          {moreSubjects > 0 ? (
            <span className="px-1 text-xs font-medium text-[var(--text-muted)]">
              +{moreSubjects} more
            </span>
          ) : null}
        </div>
      ) : null}

      {conf.url ? (
        <a
          href={conf.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-auto inline-flex items-center gap-1.5 pt-3 text-sm font-semibold text-primary hover:underline"
        >
          View conference
          <ArrowRightIcon
            size={14}
            aria-hidden="true"
            className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
          />
        </a>
      ) : null}
    </Card>
  );
}

function CardSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-6 w-24 rounded-full bg-surface-alt" />
        <span className="h-6 w-20 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/2 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
    </Card>
  );
}

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * The Conferences page: calls for papers matched to the researcher, in
 * recommendation order, as a card grid (percent match and any "New" tag lead
 * each card). Placed directly below Opportunities in the navigation.
 */
export function ConferencesSection() {
  const { data, isLoading, isError } = useConferences();
  const conferences = data?.items ?? [];

  const subtitle: React.ReactNode = (() => {
    if (isLoading) return "Gathering conferences that fit your work…";
    if (conferences.length > 0) {
      const when = formatWhen(data?.generated_at ?? null);
      const count = `${conferences.length} conference${
        conferences.length === 1 ? "" : "s"
      }`;
      return when
        ? `${count}, ranked by fit · gathered ${when}.`
        : `${count}, ranked by fit.`;
    }
    return "Conferences and calls for papers matched to your research, best fit first.";
  })();

  return (
    <div>
      <SectionHeader title="Conferences" subtitle={subtitle} />

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<ConferenceIcon size={28} />}
          title="Couldn't load your conferences"
          description="Something went wrong fetching your conference matches. Please try again in a moment."
        />
      ) : conferences.length === 0 ? (
        <EmptyState
          icon={<ConferenceIcon size={28} />}
          badge="Coming soon"
          title="Your conference matches are on their way"
          description="Once Milo's nightly scan of calls for papers runs against your research profile, the venues that best fit your work — each with a percent match and its submission deadline — will appear here as cards."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {conferences.map((conf, index) => (
            <div
              key={conf.content_id}
              className="portal-fade-up"
              style={{ animationDelay: `${index * 45}ms` }}
            >
              <ConferenceCard conf={conf} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
