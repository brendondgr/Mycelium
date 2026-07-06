"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  BankIcon,
  CalendarIcon,
  ConferenceIcon,
} from "@/components/portal/icons";
import { SaveButton, deadlineLabel } from "@/components/portal/sections/opportunity-bits";
import { useDeadlines } from "@/lib/portal/hooks";
import type { SavedDeadline } from "@/lib/portal/types";

function daysLabel(days: number | null): string {
  if (days === null) return "No date set";
  if (days < 0) return "Passed";
  if (days === 0) return "Due today";
  return `${days} day${days === 1 ? "" : "s"} left`;
}

function DeadlineRow({ item }: { item: SavedDeadline }) {
  const AreaIcon = item.area === "conference" ? ConferenceIcon : BankIcon;
  const urgent = item.within_week;

  return (
    <Card
      className="p-4"
      style={
        urgent
          ? {
              borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)",
              backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)",
            }
          : undefined
      }
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-accent">
          <AreaIcon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 className="min-w-0 font-serif text-base font-semibold leading-snug text-[var(--text-primary)]">
              {item.title}
            </h3>
            <span
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold"
              style={{
                borderColor: urgent
                  ? "color-mix(in srgb, var(--accent) 45%, transparent)"
                  : "var(--border)",
                color: urgent ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              {urgent ? <AlertTriangleIcon size={12} aria-hidden="true" /> : (
                <CalendarIcon size={12} aria-hidden="true" />
              )}
              {daysLabel(item.days_remaining)}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            {[
              item.subtitle,
              item.deadline_date
                ? deadlineLabel(item.deadline_kind, item.deadline_date)
                : "",
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>

          <div className="mt-2.5 flex flex-wrap items-center gap-3">
            {item.content_id ? (
              <SaveButton contentId={item.content_id} saved />
            ) : (
              <span className="text-xs italic text-[var(--text-muted)]">
                Original listing has closed — kept from your save.
              </span>
            )}
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
              >
                Open
                <ArrowRightIcon
                  size={13}
                  aria-hidden="true"
                  className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
                />
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </Card>
  );
}

function DeadlineSkeleton() {
  return (
    <Card className="animate-pulse p-4">
      <div className="flex items-center gap-3">
        <span className="h-8 w-8 rounded-full bg-surface-alt" />
        <span className="h-4 w-1/2 rounded bg-surface-alt" />
      </div>
    </Card>
  );
}

/**
 * The Deadlines page: everything the user saved from Opportunities or
 * Conferences, soonest first. Items due within a week are highlighted (the same
 * ones that raise a notification-bell alert). Saved snapshots persist even after
 * the source listing is pruned.
 */
export function DeadlinesSection() {
  const { data, isLoading, isError } = useDeadlines();
  const items = data?.items ?? [];
  const within = items.filter((i) => i.within_week).length;

  const subtitle = isLoading
    ? "Gathering your saved deadlines…"
    : items.length > 0
      ? within > 0
        ? `${items.length} saved · ${within} due within a week.`
        : `${items.length} saved deadline${items.length === 1 ? "" : "s"}.`
      : "Deadlines you save from Opportunities and Conferences collect here.";

  return (
    <div>
      <SectionHeader title="Deadlines" subtitle={subtitle} />

      {isLoading ? (
        <div className="space-y-3">
          <DeadlineSkeleton />
          <DeadlineSkeleton />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<CalendarIcon size={28} />}
          title="Couldn't load your deadlines"
          description="Something went wrong fetching your saved deadlines. Please try again in a moment."
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<CalendarIcon size={28} />}
          title="No deadlines saved yet"
          description="Save a grant or conference from its page and its deadline will appear here — with a warning in the notification bell once it's under a week away."
        />
      ) : (
        <div className="space-y-3">
          {items.map((item, index) => (
            <div
              key={item.id}
              className="portal-fade-up"
              style={{ animationDelay: `${index * 45}ms` }}
            >
              <DeadlineRow item={item} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
