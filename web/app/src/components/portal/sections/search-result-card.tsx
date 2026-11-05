"use client";

import {
  ArrowRightIcon,
  BankIcon,
  CalendarIcon,
  ConferenceIcon,
  DocumentIcon,
  SparkleIcon,
} from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { DiscordLink } from "@/components/portal/primitives/discord-link";
import { ClusterBadge } from "@/components/portal/primitives/cluster-badge";
import { Pill, type PillTone } from "@/components/portal/primitives/pill";
import { IgnoreButton } from "@/components/portal/sections/opportunity-bits";
import type {
  SearchContentType,
  SearchResultItem,
} from "@/lib/portal/types";

const TYPE_META: Record<
  SearchContentType,
  { label: string; tone: PillTone; icon: React.ReactNode }
> = {
  paper: { label: "Paper", tone: "neutral", icon: <DocumentIcon size={13} /> },
  grant: { label: "Grant", tone: "accent", icon: <BankIcon size={13} /> },
  fellowship: {
    label: "Fellowship",
    tone: "accent",
    icon: <SparkleIcon size={13} />,
  },
  conference: {
    label: "Conference",
    tone: "primary",
    icon: <ConferenceIcon size={13} />,
  },
};

/** The one-line context under the title, assembled per content type. */
function detailLine(item: SearchResultItem): string {
  const parts: string[] = [];
  if (item.type === "paper") {
    if (item.authors.length) {
      parts.push(
        item.authors.slice(0, 3).join(", ") +
          (item.authors.length > 3 ? " et al." : ""),
      );
    }
    if (item.venue) parts.push(item.venue);
    if (item.year) parts.push(String(item.year));
  } else if (item.type === "grant") {
    if (item.sponsor) parts.push(item.sponsor);
    if (item.amount) parts.push(item.amount);
  } else if (item.type === "fellowship") {
    if (item.award_class) {
      parts.push(item.award_class.replace(/_/g, " "));
    }
  } else if (item.type === "conference") {
    if (item.location) parts.push(item.location);
    if (item.event_dates) parts.push(item.event_dates);
  }
  return parts.join(" · ");
}

export function SearchResultCard({ item }: { item: SearchResultItem }) {
  const meta = TYPE_META[item.type];
  const detail = detailLine(item);
  return (
    <Card className="p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow)] motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={meta.tone} className="capitalize">
            {meta.icon}
            {meta.label}
          </Pill>
          {item.cluster ? <ClusterBadge cluster={item.cluster} /> : null}
          {item.deadline ? (
            <Pill tone="clay">
              <CalendarIcon size={12} />
              {item.deadline}
            </Pill>
          ) : null}
          {item.saved ? <Pill tone="primary">Saved</Pill> : null}
          {item.ignored ? <Pill tone="neutral">Ignored</Pill> : null}
        </div>
        {/* Search deliberately still returns ignored hits — you typed the query
            — so this is both the way to dismiss a result and the way back. */}
        <IgnoreButton
          contentId={item.content_id}
          title={item.title}
          ignored={item.ignored}
        />
      </div>

      <h3 className="mt-2.5 font-serif text-lg font-semibold leading-snug text-[var(--text-primary)]">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {item.title}
          </a>
        ) : (
          item.title
        )}
      </h3>

      {detail ? (
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{detail}</p>
      ) : null}

      {item.summary ? (
        <p className="mt-2.5 line-clamp-3 text-sm leading-relaxed text-[var(--text-secondary)]">
          {item.summary}
        </p>
      ) : null}

      <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Open {meta.label.toLowerCase()}
            <ArrowRightIcon size={14} />
          </a>
        ) : null}
        {item.discord?.length ? (
          <span className="inline-flex items-center gap-1 text-[13px] text-[var(--text-secondary)]">
            Discussed in Discord
            <DiscordLink links={item.discord} surface="search" />
          </span>
        ) : null}
      </div>
    </Card>
  );
}
