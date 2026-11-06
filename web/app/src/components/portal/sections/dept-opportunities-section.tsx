"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { DiscordLink } from "@/components/portal/primitives/discord-link";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CheckPill } from "@/components/portal/primitives/usability-strip";
import { usePortal } from "@/components/portal/portal-context";
import { useDeptOpportunities } from "@/lib/portal/hooks";
import type { DeptOpportunity } from "@/lib/portal/types";

const KIND_LABEL: Record<string, string> = {
  grant: "Grant",
  fellowship: "Fellowship",
  conference: "Conference",
};

function longDate(iso: string): string {
  if (!iso) return "";
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * A department's Opportunities page (plan "What a department sees"): only the
 * calls a lab could not take on alone, each saying why with the sentence it
 * matched, and naming the labs that could lead — never people. A fellowship shows
 * counts only; each eligible member is told privately.
 */
export function DeptOpportunitiesSection() {
  const { currentDepartment } = usePortal();
  const { data, isLoading, isError } = useDeptOpportunities(
    currentDepartment?.id ?? null,
  );
  const name = currentDepartment?.name ?? "a department";

  return (
    <div>
      <SectionHeader
        eyebrow="Department"
        title="Opportunities"
        subtitle={`Calls only ${name} can take on as a department: limited submissions, department applicants, training programmes and centres.`}
      />
      {!currentDepartment ? (
        <EmptyState
          title="Pick a department"
          description="Switch to a department workspace to see the calls it can take on."
        />
      ) : isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]" role="status">
          Loading the department&apos;s opportunities…
        </p>
      ) : isError ? (
        <EmptyState
          title="Couldn't load these"
          description="Something went wrong reading the department's opportunities. Try again in a moment."
        />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="Nothing department-level right now"
          description={
            data?.announcements_on
              ? "Nothing on the department's list needs a department to apply. Calls a lab can take on alone stay with the labs."
              : "The department is matched only while its announcements are on. A department admin can switch them on in Department settings."
          }
        />
      ) : (
        <DeptOpportunityList items={data.items} />
      )}
    </div>
  );
}

function DeptOpportunityList({ items }: { items: DeptOpportunity[] }) {
  const live = items.filter((i) => !i.held);
  const held = items.filter((i) => i.held);
  return (
    <>
      {live.length ? (
        <ul className="flex flex-col gap-3">
          {live.map((item) => (
            <DeptOpportunityCard key={item.content_id} item={item} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-[var(--text-secondary)]">
          Nothing department-level is open right now.
        </p>
      )}
      {held.length ? (
        <section
          aria-labelledby="dept-held-back"
          className="mt-6 rounded-xl bg-surface-alt p-4"
        >
          <h2
            id="dept-held-back"
            className="m-0 font-serif text-lg font-semibold text-[var(--text-primary)]"
          >
            Mylo held back
          </h2>
          <p className="m-0 mb-2 text-[13px] text-[var(--text-secondary)]">
            Department-level, but failed a hard check, so Mylo won&apos;t post them.
          </p>
          <ul className="flex flex-col gap-2">
            {held.map((item) => (
              <li
                key={item.content_id}
                className="rounded-lg border border-border bg-surface p-3"
              >
                <span className="block break-words text-[14px] font-semibold text-[var(--text-primary)]">
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}
                </span>
                <span className="text-[13px] text-[var(--text-secondary)]">
                  {item.reasons.map((r) => r.label).join(" · ")} · {item.held}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function DeptOpportunityCard({ item }: { item: DeptOpportunity }) {
  const checks = item.checks.filter((c) => c.key !== "team");
  return (
    <li>
      <Card className="p-4 sm:p-5">
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <Pill tone="neutral">{KIND_LABEL[item.category] ?? item.category}</Pill>
          {item.reasons.map((r) => (
            <Pill key={r.key} tone="accent">
              {r.label}
            </Pill>
          ))}
        </div>
        <h2 className="m-0 font-serif text-[18px] font-medium leading-snug text-[var(--text-primary)]">
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </h2>
        {item.funder ? (
          <p className="m-0 text-[13px] text-[var(--text-secondary)]">{item.funder}</p>
        ) : null}

        <section
          aria-label="Why it's here"
          className="mt-3 flex flex-col gap-2 rounded-xl border border-[var(--divider)] bg-surface-alt p-3"
        >
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
            Why it&apos;s here
          </h3>
          {item.reasons.map((r) => (
            <figure key={r.key} className="m-0">
              <figcaption className="text-[13px] font-semibold text-[var(--text-primary)]">
                {r.label}
              </figcaption>
              <blockquote className="m-0 mt-0.5 break-words border-l-2 border-border pl-2.5 text-[13px] italic leading-relaxed text-[var(--text-secondary)]">
                {r.evidence}
              </blockquote>
            </figure>
          ))}
        </section>

        {checks.length ? (
          <ul aria-label="Can we use this?" className="mt-3 flex flex-wrap gap-1.5">
            {checks.map((c) => (
              <CheckPill key={c.key} check={c} />
            ))}
          </ul>
        ) : null}

        <p className="m-0 mt-3 text-[13px] text-[var(--text-primary)]">
          <span className="text-[var(--text-secondary)]">Labs that could lead: </span>
          {item.labs.length ? (
            item.labs.map((lab, i) => (
              <React.Fragment key={lab.name}>
                {i ? " · " : ""}
                <strong className="font-semibold">{lab.name}</strong>
              </React.Fragment>
            ))
          ) : (
            <span className="text-[var(--text-secondary)]">
              no lab&apos;s profile matches it closely
            </span>
          )}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--divider)] pt-2 text-[13px] text-[var(--text-secondary)]">
          {item.deadline ? (
            <span>
              Due <strong className="text-[var(--text-primary)]">{longDate(item.deadline)}</strong>
            </span>
          ) : null}
          {item.announced ? (
            <DiscordLink
              links={item.discord}
              fallbackChannel="dept-opportunities"
              surface="dept_page"
              className="ml-auto"
            />
          ) : (
            <span className="ml-auto">Not announced yet</span>
          )}
        </div>
      </Card>
    </li>
  );
}
