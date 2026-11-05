"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { DiscordLink } from "@/components/portal/primitives/discord-link";
import { Modal } from "@/components/portal/primitives/modal";
import { CheckPill } from "@/components/portal/primitives/usability-strip";
import type {
  AnnouncedItem,
  AnnouncementsResponse,
  ClosingSoonItem,
} from "@/lib/portal/types";

const KIND_LABEL: Record<string, string> = {
  grant: "Grant",
  fellowship: "Fellowship",
  conference: "Conference",
};
const FORUM: Record<string, string> = {
  grant: "grants",
  fellowship: "fellowships",
  conference: "conferences",
};

function shortDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function PanelTitle({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <h2 className="font-serif text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
      {children}
    </div>
  );
}

/**
 * The lab overview's "Announced" panel (replaces "What Mylo found"): the last few
 * threads Mylo posted, each with its Discord link, and the full list — including
 * what Mylo held back and why — one click away.
 */
export function AnnouncedPanel({
  data,
  isLoading,
  isError,
}: {
  data: AnnouncementsResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const items = data?.announced ?? [];
  return (
    <Card className="p-5">
      <PanelTitle title="Announced">
        {data && (items.length || data.held.length) ? (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="min-h-[32px] text-left text-[13px] font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            See all, and what Mylo held back
          </button>
        ) : null}
      </PanelTitle>
      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading announcements…</p>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load announcements. Try again in a moment.
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Nothing announced yet. New grants, fellowships and conferences that fit the
          lab get their own Discord thread here.
        </p>
      ) : (
        <ul className="divide-y divide-[var(--divider)]">
          {items.slice(0, 3).map((item) => (
            <li key={item.id} className="flex flex-col gap-1 py-2.5 first:pt-0">
              <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
                {KIND_LABEL[item.category] ?? item.category}
                {item.updated_on.length ? " · Updated" : ""}
              </span>
              <span className="text-[14px] font-semibold leading-snug text-[var(--text-primary)]">
                {item.title}
              </span>
              <span className="flex flex-wrap items-center gap-x-2 text-[13px] text-[var(--text-secondary)]">
                {item.deadline ? <span>{shortDate(item.deadline)}</span> : null}
                {item.interested ? <span>{item.interested} interested</span> : null}
                <DiscordLink links={item.discord} fallbackChannel={FORUM[item.category]} surface="announced" />
              </span>
            </li>
          ))}
        </ul>
      )}
      {open && data ? (
        <AnnouncedModal data={data} onClose={() => setOpen(false)} />
      ) : null}
    </Card>
  );
}

function AnnouncedModal({
  data,
  onClose,
}: {
  data: AnnouncementsResponse;
  onClose: () => void;
}) {
  const [kind, setKind] = React.useState<string>("all");
  const rows = data.announced.filter((r) => kind === "all" || r.category === kind);
  return (
    <Modal onClose={onClose} label="Announced, and what Mylo held back" width="lg">
      <div className="flex max-h-[80vh] flex-col gap-4 overflow-y-auto p-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="m-0 font-serif text-2xl font-semibold text-[var(--text-primary)]">
              Announced
            </h2>
            <p className="m-0 text-[13px] text-[var(--text-secondary)]">
              One Discord thread per item, and what Mylo held back with the reason.
            </p>
          </div>
          <div role="group" aria-label="Show" className="flex flex-wrap gap-1.5">
            {["all", "grant", "fellowship", "conference"].map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={kind === k}
                onClick={() => setKind(k)}
                className={
                  "min-h-[36px] rounded-full border px-3 text-[13px] font-semibold " +
                  (kind === k
                    ? "border-primary bg-primary text-white"
                    : "border-border bg-surface text-[var(--text-secondary)]")
                }
              >
                {k === "all" ? "All" : `${KIND_LABEL[k]}s`}
              </button>
            ))}
          </div>
        </div>
        <ul className="flex flex-col gap-3">
          {rows.map((row) => (
            <AnnouncedRow key={row.id} row={row} />
          ))}
          {rows.length === 0 ? (
            <li className="text-sm text-[var(--text-secondary)]">Nothing here yet.</li>
          ) : null}
        </ul>
        {data.held.length ? (
          <section aria-labelledby="held-back" className="rounded-xl bg-surface-alt p-4">
            <h3 id="held-back" className="m-0 font-serif text-lg font-semibold text-[var(--text-primary)]">
              Mylo held back
            </h3>
            <p className="m-0 mb-2 text-[13px] text-[var(--text-secondary)]">
              These fit your themes but failed a hard check, so they were never posted.
            </p>
            <ul className="flex flex-col gap-2">
              {data.held.map((h) => (
                <li key={h.id} className="rounded-lg border border-border bg-surface p-3">
                  <span className="block text-[14px] font-semibold text-[var(--text-primary)]">
                    {h.url ? (
                      <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                        {h.title}
                      </a>
                    ) : (
                      h.title
                    )}
                  </span>
                  <span className="text-[13px] text-[var(--text-secondary)]">{h.reason}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </Modal>
  );
}

function AnnouncedRow({ row }: { row: AnnouncedItem }) {
  return (
    <li className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-secondary)]">
        <span className="rounded-full bg-surface-alt px-2 py-0.5 font-semibold uppercase tracking-[0.05em]">
          {KIND_LABEL[row.category]}
        </span>
        <span>{row.updated_on.length ? `Updated ${shortDate(row.updated_on[row.updated_on.length - 1])}` : row.label_text}</span>
        <span className="ml-auto">Posted {shortDate(row.posted_at)}</span>
      </div>
      <h3 className="m-0 font-serif text-[18px] font-medium leading-snug text-[var(--text-primary)]">
        {row.title}
      </h3>
      {row.funder ? <p className="m-0 text-[13px] text-[var(--text-secondary)]">{row.funder}</p> : null}
      {row.checks.length ? (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {row.checks
            .filter((c) => c.key !== "team")
            .map((c) => (
              <CheckPill key={c.key} check={c} />
            ))}
        </ul>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--divider)] pt-2 text-[13px] text-[var(--text-secondary)]">
        {row.deadline ? (
          <span>
            <strong className="text-[var(--text-primary)]">{shortDate(row.deadline)}</strong>
          </span>
        ) : null}
        <span>{row.interested ? `${row.interested} interested` : "No reactions yet"}</span>
        <DiscordLink links={row.discord} fallbackChannel={FORUM[row.category]} surface="announced" className="ml-auto" />
      </div>
    </li>
  );
}

/**
 * "Closing soon · 14 days" (replaces "Deadlines"): the same list Mylo posts in
 * Discord each morning, saved items included.
 */
export function ClosingSoonPanel({
  items,
  isLoading,
  isError,
}: {
  items: ClosingSoonItem[];
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <Card className="p-5">
      <PanelTitle title="Closing soon · 14 days" />
      <p className="-mt-2 mb-3 text-[13px] text-[var(--text-secondary)]">
        The same list Mylo posts in Discord each morning.
      </p>
      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load the list.</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Nothing on the lab&apos;s list closes in the next two weeks.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.slice(0, 6).map((item) => (
            <li key={item.content_id} className="flex items-baseline gap-3 text-[14px]">
              <span className="w-[86px] shrink-0 font-semibold text-[var(--text-primary)]">
                {item.days === 0 ? "Today" : shortDate(item.due)}
              </span>
              <span className="min-w-0 flex-1">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-[var(--text-primary)] hover:underline">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
                {item.discord.length ? (
                  <DiscordLink links={item.discord} fallbackChannel={FORUM[item.category]} surface="closing_soon" className="ml-1" />
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
