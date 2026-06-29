"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CheckIcon, TargetIcon } from "@/components/portal/icons";
import { useProfile, useWatch } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";

// ---------------------------------------------------------------------------
// Research focus card (LEFT)
// ---------------------------------------------------------------------------

function ResearchFocusCard() {
  const { data: profile, isLoading, isError } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
          Research focus
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Loading your profile…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
          Research focus
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Couldn&apos;t load your profile.</p>
      </Card>
    );
  }

  const interests = profile?.interests;
  const areas = interests?.areas ?? [];
  const statement = interests?.statement?.trim() ?? "";
  const keywords = interests?.keywords ?? [];
  const methods = interests?.methods ?? [];
  const skills = interests?.skills ?? [];

  return (
    <Card className="p-[22px]">
      <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
        Research focus
      </h2>

      {/* Statement */}
      {statement ? (
        <p className="mb-4 text-sm leading-relaxed text-[var(--text-secondary)]">
          {statement}
        </p>
      ) : null}

      {/* Areas */}
      {areas.length > 0 ? (
        <div className="mb-4 flex flex-col gap-2.5">
          {areas.map((area) => (
            <div key={area} className="flex items-start gap-2.5">
              <TargetIcon
                size={18}
                className="mt-0.5 shrink-0 text-primary"
              />
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {area}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mb-4 text-sm text-[var(--text-muted)]">
          Add research areas in your profile so Mylo can match work to you.
        </p>
      )}

      {/* Keyword / method / skill chip groups */}
      {[
        { label: "Keywords", items: keywords },
        { label: "Methods", items: methods },
        { label: "Skills", items: skills },
      ]
        .filter(({ items }) => items.length > 0)
        .map(({ label, items }) => (
          <div key={label} className="mb-3">
            <p className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
              {label}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {items.map((item) => (
                <Pill key={item} tone="neutral">
                  {item}
                </Pill>
              ))}
            </div>
          </div>
        ))}

      <p className="mt-4 text-[11.5px] text-[var(--text-muted)]">
        Editing your profile from the dashboard is coming soon.
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Profile completeness card (RIGHT top)
// ---------------------------------------------------------------------------

function ProfileCompletenessCard() {
  const { data: profile, isLoading, isError } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Profile completeness
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Profile completeness
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Couldn&apos;t load your profile.</p>
      </Card>
    );
  }

  const { percent, items } = computeCompleteness(profile);

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Profile completeness
      </h2>

      <div className="my-2.5 flex justify-between text-xs font-medium">
        <span className="text-[var(--text-secondary)]">Completeness</span>
        <span className="font-semibold text-[var(--text-secondary)]">{percent}%</span>
      </div>

      <ProgressBar
        value={percent}
        tone="primary"
        label="Profile completeness"
        className="mb-4"
      />

      <div className="flex flex-col gap-2.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2.5 text-sm">
            {item.done ? (
              <CheckIcon
                size={16}
                className="shrink-0 text-primary"
                aria-hidden="true"
              />
            ) : (
              <span
                className="inline-block h-4 w-4 shrink-0 rounded-full border border-[var(--text-muted)]"
                aria-hidden="true"
              />
            )}
            <span
              className={
                item.done
                  ? "text-[var(--text-primary)]"
                  : "text-[var(--text-muted)]"
              }
            >
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// What Milo watches card (RIGHT bottom)
// ---------------------------------------------------------------------------

function WatchCard() {
  const { data: watch, isLoading, isError } = useWatch();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          What Milo watches
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          What Milo watches
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Couldn&apos;t load your watch settings.</p>
      </Card>
    );
  }

  const topics = watch?.topics ?? [];
  const categories = watch?.categories ?? [];
  const cadence = watch?.cadence ?? "weekly";

  const cadenceLabel =
    cadence === "realtime" ? "real-time" : cadence === "daily" ? "daily" : "weekly";

  return (
    <Card className="p-[22px]">
      <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
        What Milo watches
      </h2>

      {topics.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">
          You haven&apos;t set watch topics yet.
        </p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {topics.map((topic) => (
              <Pill key={topic} tone="neutral">
                {topic}
              </Pill>
            ))}
          </div>

          {categories.length > 0 ? (
            <p className="mb-1.5 text-xs text-[var(--text-secondary)]">
              Signals:{" "}
              <span className="font-medium">{categories.join(", ")}</span>
            </p>
          ) : null}

          <p className="text-xs text-[var(--text-secondary)]">
            Cadence:{" "}
            <span className="font-medium">{cadenceLabel} digest</span>
          </p>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// GoalsSection
// ---------------------------------------------------------------------------

export function GoalsSection() {
  return (
    <div>
      <SectionHeader
        title="Goals & profile"
        subtitle="What you're working toward, and what Mylo uses to find matches."
      />

      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-[1.3fr_1fr] lg:items-start">
        {/* LEFT — research focus */}
        <ResearchFocusCard />

        {/* RIGHT — stacked completeness + watch */}
        <div className="flex flex-col gap-[22px]">
          <ProfileCompletenessCard />
          <WatchCard />
        </div>
      </div>
    </div>
  );
}
