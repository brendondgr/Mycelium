"use client";

import * as React from "react";
import Link from "next/link";

import { BankIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { Pill } from "@/components/portal/primitives/pill";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { LabPlanCard } from "@/components/portal/sections/org-plan-card";
import { PlansCard } from "@/components/portal/sections/plans-card";
import { useEntitlements, useLabBilling } from "@/lib/portal/hooks";
import type { Entitlements, MyLab } from "@/lib/portal/types";

const TIER_LABEL: Record<Entitlements["tier"], string> = {
  free: "Free",
  spore: "Spore",
  lab: "Mycelium Lab",
  canopy: "Canopy",
};

/** Owner/admin/PI — the roles that may see and act on a lab's money. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/**
 * Billing — the one place plans, prices, and anything else monetary live.
 *
 * Split out of the settings surfaces on purpose: "Your plans" used to sit in the
 * personal Profile and the lab plan in Lab settings, which put pricing in front of
 * anyone editing a research focus. Scope-aware like the rest of the workspace: the
 * personal scope shows the account's own plans, a lab scope shows that lab's plan
 * (managers only — a member has no business reading the lab's invoice).
 */
export function BillingSection() {
  const { currentLab } = usePortal();
  return currentLab ? <LabBilling lab={currentLab} /> : <PersonalBilling />;
}

// -- personal -----------------------------------------------------------------

function PersonalBilling() {
  return (
    <div>
      <SectionHeader
        eyebrow="Workspace"
        title="Billing"
        subtitle="The plans on your account, what each one unlocks, and who pays for it."
      />
      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-[1.3fr_1fr] lg:items-start">
        <div className="flex flex-col gap-[22px]">
          <PlansCard />
          <TeamPlanCard />
        </div>
        <div className="flex flex-col gap-[22px]">
          <CurrentPlanCard />
        </div>
      </div>
    </div>
  );
}

/**
 * Where a team plan actually comes from.
 *
 * Mycelium Lab is priced per member, so it is activated on a lab — the lab has the
 * roster that sets the price, and activating there covers everyone in it at once. A
 * personal account has nobody to count, which is why it cannot hold one. Rather than
 * leave that as an unexplained absence, say it here and point at the lab.
 */
function TeamPlanCard() {
  const { labs } = usePortal();
  const managed = (labs ?? []).filter(canManageLab);

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Working with a team?
      </h2>
      <p className="mb-3 text-xs text-[var(--text-secondary)]">
        Mycelium Lab covers a whole research group.
      </p>
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        A lab plan is activated on the lab itself, not here — the lab&apos;s roster is
        what sets the price, and switching it on covers every member at once, you
        included. You need to be the PI, owner, or an admin of the lab.
      </p>
      {managed.length > 0 ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          {managed.length === 1 ? "Your lab: " : "Your labs: "}
          {managed.map((lab, index) => (
            <React.Fragment key={lab.slug}>
              {index > 0 ? ", " : ""}
              <Link
                href={`/app/${lab.slug}/dashboard`}
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                {lab.name}
              </Link>
            </React.Fragment>
          ))}
          . Switch to it in the workspace switcher, then open Billing there.
        </p>
      ) : (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          You don&apos;t manage a lab yet.{" "}
          <Link
            href="/app/labs"
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            Create one
          </Link>{" "}
          — the workspace itself is free — then activate its plan from the lab&apos;s own
          Billing page.
        </p>
      )}
    </Card>
  );
}

/** What the account's effective plan actually grants, in the plan's own numbers. */
function CurrentPlanCard() {
  const { data, isLoading, isError } = useEntitlements();

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Your current plan
      </h2>
      <p className="mb-3 text-xs text-[var(--text-secondary)]">
        The highest plan covering you, and the limits it sets.
      </p>

      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading your plan…</p>
      ) : isError || !data ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load your plan.
        </p>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2">
            <span className="font-serif text-lg font-semibold text-[var(--text-primary)]">
              {TIER_LABEL[data.tier]}
            </span>
            <Pill tone={data.tier === "free" ? "neutral" : "primary"}>
              {data.tier === "free" ? "Free" : "Paid"}
            </Pill>
          </div>
          <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
            <dt className="text-[var(--text-secondary)]">Subjects watched</dt>
            <dd className="text-right font-medium text-[var(--text-primary)]">
              {data.topics_used} / {data.topic_cap}
            </dd>
            <dt className="text-[var(--text-secondary)]">Research clusters</dt>
            <dd className="text-right font-medium text-[var(--text-primary)]">
              {data.cluster_cap}
            </dd>
            <dt className="text-[var(--text-secondary)]">Topics per cluster</dt>
            <dd className="text-right font-medium text-[var(--text-primary)]">
              {data.cluster_topic_cap}
            </dd>
          </dl>
          {data.tier === "free" ? (
            <p className="mt-3 text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
              Free searches and scores on demand. A paid plan adds Mylo&apos;s reasoned
              fit verdicts, scheduled reports, and grant, fellowship, and conference
              alerts.
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}

// -- lab ----------------------------------------------------------------------

function LabBilling({ lab }: { lab: MyLab }) {
  if (!canManageLab(lab)) {
    return (
      <div>
        <SectionHeader eyebrow="Workspace" title="Billing" />
        <EmptyState
          icon={<BankIcon size={28} />}
          badge="Restricted"
          title="Only lab managers can see the lab's billing"
          description="A lab lead, owner, or admin manages the plan and what it costs. Your own plans are on your personal Billing page."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        title={`${lab.name} billing`}
        subtitle="This lab's plan, what it covers, and what it costs per member."
      />
      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-[1.3fr_1fr] lg:items-start">
        <div className="flex flex-col gap-[22px]">
          <LabPlanCard slug={lab.slug} />
        </div>
        <div className="flex flex-col gap-[22px]">
          <LabAddOnsCard lab={lab} />
        </div>
      </div>
    </div>
  );
}

/**
 * Capabilities that sit beside the tier rather than inside it. Mylo on Discord is the
 * only one today, and it is the gate the lab's Discord setup card reads — so this card
 * is where a manager finds out *why* that flow is locked.
 */
function LabAddOnsCard({ lab }: { lab: MyLab }) {
  const { data, isLoading, isError } = useLabBilling(lab.slug);
  const included = Boolean(data?.mylo_included);

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Add-ons
      </h2>
      <p className="mb-3 text-xs text-[var(--text-secondary)]">
        Extras that attach to the plan, separate from its tier.
      </p>

      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading add-ons…</p>
      ) : isError || !data ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load this lab&apos;s add-ons.
        </p>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3 py-1.5">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Mylo on Discord
              </p>
              <p className="text-xs text-[var(--text-secondary)]">
                Mylo joins your server to post deadlines, digests, and reminders.
              </p>
            </div>
            <Pill tone={included ? "primary" : "dashed"}>
              {included ? "Included" : "Not included"}
            </Pill>
          </div>
          {included ? (
            <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
              Connect a server from{" "}
              <Link
                href="/app/profile"
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Lab settings
              </Link>
              .
            </p>
          ) : (
            <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
              Mylo isn&apos;t on this plan, so the lab can&apos;t add him to a Discord
              server yet. Contact us to add him and the setup flow unlocks.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
