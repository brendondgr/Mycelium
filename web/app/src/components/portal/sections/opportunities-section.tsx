"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  ArrowRightIcon,
  BankIcon,
  CalendarIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import {
  MatchBadge,
  NewTag,
  SaveButton,
  deadlineLabel,
} from "@/components/portal/sections/opportunity-bits";
import { useGrants } from "@/lib/portal/hooks";
import type { GrantOpportunity } from "@/lib/portal/types";

/** A compact fact chip (funding amount, application due date) beside the hosts. */
function DetailTag({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
      {icon}
      {children}
    </span>
  );
}

/** Format an ISO first-seen date for the "Posted" line ("Jul 6, 2026"). */
function postedLabel(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function GrantRow({ grant }: { grant: GrantOpportunity }) {
  const dueLabel = deadlineLabel(grant.deadline_kind, grant.deadline_date);
  const posted = postedLabel(grant.posted);
  const topics = grant.matched_topics
    .split(";")
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 5);
  const isMylo = grant.origin === "llm";
  const hasChips = grant.is_new || Boolean(grant.amount) || Boolean(dueLabel);

  return (
    <Card className="p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      {/* Title shares its row with the fit score and a round save bookmark. */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
          {grant.title}
        </h3>
        <div className="flex shrink-0 items-center gap-2">
          <MatchBadge percent={grant.match_percent} />
          <SaveButton
            contentId={grant.content_id}
            saved={grant.saved}
            variant="icon"
          />
        </div>
      </div>

      {/* Hosts on the left; the funding amount and due date as chips on the right. */}
      {grant.sponsor || hasChips ? (
        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
          {grant.sponsor ? (
            <p className="min-w-0 text-xs font-medium text-[var(--text-secondary)]">
              {grant.sponsor}
            </p>
          ) : (
            <span aria-hidden="true" />
          )}
          {hasChips ? (
            <div className="flex flex-wrap items-center gap-2">
              {grant.is_new ? <NewTag /> : null}
              {grant.amount ? (
                <DetailTag icon={<BankIcon size={12} aria-hidden="true" />}>
                  {grant.amount}
                </DetailTag>
              ) : null}
              {dueLabel ? (
                <DetailTag icon={<CalendarIcon size={12} aria-hidden="true" />}>
                  {dueLabel}
                </DetailTag>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {posted ? (
        <p className="mt-2 text-xs text-[var(--text-muted)]">Posted {posted}</p>
      ) : null}

      {grant.description ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          {grant.description}
        </p>
      ) : null}

      {/* Milo's read on why this fits the user, with his mark (like the Lab editor). */}
      {grant.reason ? (
        <div className="mt-2.5 flex items-start gap-2">
          {isMylo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src="/mylo-headshot.webp"
              alt=""
              width={20}
              height={20}
              className="mt-0.5 h-5 w-5 shrink-0 rounded-full object-cover"
            />
          ) : null}
          <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
            {grant.reason}
          </p>
        </div>
      ) : null}

      {topics.length > 0 ? (
        <p className="mt-2.5 text-xs text-[var(--text-muted)]">
          Matched: {topics.join(" · ")}
        </p>
      ) : null}

      {grant.url ? (
        <a
          href={grant.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
        >
          View opportunity
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

function GrantSkeleton() {
  return (
    <Card className="animate-pulse p-5">
      <div className="flex items-center justify-between">
        <span className="h-5 w-20 rounded-full bg-surface-alt" />
        <span className="h-6 w-24 rounded-full bg-surface-alt" />
      </div>
      <span className="mt-3 block h-4 w-3/4 rounded bg-surface-alt" />
      <span className="mt-2 block h-3 w-1/2 rounded bg-surface-alt" />
      <span className="mt-3 block h-3 w-full rounded bg-surface-alt" />
    </Card>
  );
}

function GrantsColumn() {
  const { data, isLoading, isError } = useGrants();
  const grants = data?.items ?? [];

  return (
    <section aria-labelledby="grants-heading">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] text-accent">
          <BankIcon size={16} />
        </span>
        <h2
          id="grants-heading"
          className="font-serif text-xl font-semibold text-[var(--text-primary)]"
        >
          Grants
        </h2>
      </div>

      {isLoading ? (
        <div className="space-y-3.5">
          <GrantSkeleton />
          <GrantSkeleton />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<BankIcon size={26} className="text-accent" />}
          title="Couldn't load your grants"
          description="Something went wrong fetching your funding matches. Please try again in a moment."
        />
      ) : grants.length === 0 ? (
        <EmptyState
          icon={<BankIcon size={26} className="text-accent" />}
          badge="Coming soon"
          title="Your grant matches are on their way"
          description="Once Milo's nightly funding scan runs against your research profile, your best-fit grants — each with a percent-match score, its deadline, and why it fits — will appear here, newest strong matches pinned to the top."
        />
      ) : (
        <div className="space-y-3.5">
          {grants.map((grant, index) => (
            <div
              key={grant.content_id}
              className="portal-fade-up"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <GrantRow grant={grant} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function FellowshipsColumn() {
  return (
    <section aria-labelledby="fellowships-heading">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] text-primary">
          <SparkleIcon size={16} />
        </span>
        <h2
          id="fellowships-heading"
          className="font-serif text-xl font-semibold text-[var(--text-primary)]"
        >
          Fellowships
        </h2>
      </div>
      <EmptyState
        icon={<SparkleIcon size={26} className="text-accent" />}
        badge="In progress"
        title="Fellowship matching is being designed"
        description="Fellowships are matched to a person's stage, eligibility, and timeline — a distinct approach we're still shaping. They'll join this column once the matcher is ready."
      />
    </section>
  );
}

/**
 * The Opportunities page: a two-column layout with matched funding (grants) on
 * the left in a scannable, detail-forward row format, and fellowships on the
 * right as an honest work-in-progress. Conferences live on their own page.
 */
export function OpportunitiesSection() {
  return (
    <div>
      <SectionHeader
        title="Opportunities"
        subtitle="Grants and fellowships matched to your profile and timeline."
      />
      <div className="grid grid-cols-1 gap-x-8 gap-y-8 lg:grid-cols-[1.5fr_1fr]">
        <GrantsColumn />
        <FellowshipsColumn />
      </div>
    </div>
  );
}
