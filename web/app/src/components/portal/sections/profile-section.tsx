"use client";

import * as React from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CheckIcon, TargetIcon } from "@/components/portal/icons";
import { useProfile, useWatch } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";
import type { ProfileEligibility } from "@/lib/auth-types";

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

      {/* Keyword / skill chip groups */}
      {[
        { label: "Keywords", items: keywords },
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
// What Mylo watches card (RIGHT bottom)
// ---------------------------------------------------------------------------

function WatchCard() {
  const { data: watch, isLoading, isError } = useWatch();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          What Mylo watches
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          What Mylo watches
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Couldn&apos;t load your watch settings.</p>
      </Card>
    );
  }

  const topics = watch?.topics ?? [];
  const categories = watch?.categories ?? [];
  const cadence = watch?.cadence ?? "weekly";

  const cadenceLabel = cadence === "daily" ? "daily" : "weekly";

  return (
    <Card className="p-[22px]">
      <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
        What Mylo watches
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
// Eligibility helpers
// ---------------------------------------------------------------------------

const CITIZENSHIP_LABEL: Record<ProfileEligibility["citizenship"], string> = {
  us: "US citizen / permanent resident",
  international: "International student",
};

const STAGE_LABEL: Record<ProfileEligibility["stage"], string> = {
  masters: "Master's",
  doctoral_early: "Early doctoral",
  doctoral_dissertation: "Dissertation research / write-up",
  postdoc: "Postdoc / beyond",
  "": "Not specified",
};

// ---------------------------------------------------------------------------
// Fellowship eligibility card
// ---------------------------------------------------------------------------

function EligibilityCard() {
  const { data: profile, isLoading, isError } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Fellowship eligibility
        </h2>
        <p className="text-sm text-[var(--text-muted)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Fellowship eligibility
        </h2>
        <p className="text-sm text-[var(--text-muted)]">
          Couldn&apos;t load your eligibility details.
        </p>
      </Card>
    );
  }

  const eligibility = profile?.interests?.eligibility;

  if (!eligibility) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-2 text-base font-semibold text-[var(--text-primary)]">
          Fellowship eligibility
        </h2>
        <p className="text-sm text-[var(--text-muted)]">
          Fellowship matching uses your eligibility profile — citizenship,
          career stage, and field. Set it from{" "}
          <Link
            href="/app/onboarding?edit=1"
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            Edit profile
          </Link>
          .
        </p>
      </Card>
    );
  }

  const citizenshipLabel = CITIZENSHIP_LABEL[eligibility.citizenship] ?? eligibility.citizenship;
  const stageLabel = STAGE_LABEL[eligibility.stage] ?? eligibility.stage;
  const fields = eligibility.fields ?? [];
  const restrictions = eligibility.eligible_restrictions ?? [];

  return (
    <Card className="p-[22px]">
      <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
        Fellowship eligibility
      </h2>

      <div className="space-y-3">
        {/* Citizenship */}
        <div className="flex flex-col gap-0.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
            Citizenship
          </p>
          <p className="text-sm text-[var(--text-primary)]">{citizenshipLabel}</p>
        </div>

        {/* Stage */}
        <div className="flex flex-col gap-0.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
            Career stage
          </p>
          <p className="text-sm text-[var(--text-primary)]">{stageLabel}</p>
        </div>

        {/* Broad fields */}
        <div className="flex flex-col gap-1.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
            Broad fields
          </p>
          {fields.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {fields.map((field) => (
                <Pill key={field} tone="primary">
                  {field}
                </Pill>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">None selected</p>
          )}
        </div>

        {/* Restriction groups */}
        <div className="flex flex-col gap-1.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-muted)]">
            Eligible restriction groups
          </p>
          {restrictions.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {restrictions.map((r) => (
                <Pill key={r} tone="accent">
                  {r}
                </Pill>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">None selected</p>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// ProfileSection
// ---------------------------------------------------------------------------

export function ProfileSection() {
  return (
    <div>
      <SectionHeader
        title="Profile"
        subtitle="Your research focus and goals — what Mylo uses to find matches."
        action={
          <Button asChild className="rounded-full">
            <Link href="/app/onboarding?edit=1">Edit profile</Link>
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-[1.3fr_1fr] lg:items-start">
        {/* LEFT — research focus */}
        <ResearchFocusCard />

        {/* RIGHT — stacked completeness + eligibility + watch */}
        <div className="flex flex-col gap-[22px]">
          <ProfileCompletenessCard />
          <EligibilityCard />
          <WatchCard />
        </div>
      </div>
    </div>
  );
}
