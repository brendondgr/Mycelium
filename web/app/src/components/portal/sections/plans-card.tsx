"use client";

import { useAppHref } from "@/components/demo/demo-context";
import Link from "next/link";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import { useEntitlements } from "@/lib/portal/hooks";
import type { PlanSummary } from "@/lib/portal/types";

const TIER_LABEL: Record<PlanSummary["tier"], string> = {
  free: "Free",
  spore: "Spore",
  lab: "Mycelium Lab",
  canopy: "Canopy",
};

const SCOPE_LABEL: Record<PlanSummary["scope_type"], string> = {
  personal: "Personal",
  lab: "Lab",
  department: "Department",
};

const PAYER_LABEL: Record<string, string> = {
  self: "You pay",
  lab: "Lab-paid",
  department: "Department-paid",
};

/** Whether a plan is currently granting entitlements (drives the badge). */
function isLive(plan: PlanSummary): boolean {
  if (plan.scope_type === "personal") {
    return plan.status === "active";
  }
  return plan.status === "active" && plan.seat_status === "active";
}

function PlanRow({ plan }: { plan: PlanSummary }) {
  const appHref = useAppHref();
  const live = isLive(plan);
  const paid = plan.tier !== "free";
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {TIER_LABEL[plan.tier]}
          </span>
          <Pill tone={paid ? "primary" : "neutral"} className="px-2 py-0.5">
            {SCOPE_LABEL[plan.scope_type]}
          </Pill>
        </div>
        <span className="truncate text-xs text-[var(--text-secondary)]">
          {plan.scope_name}
          {plan.payer_type && PAYER_LABEL[plan.payer_type]
            ? ` · ${PAYER_LABEL[plan.payer_type]}`
            : ""}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Pill tone={live ? "primary" : "dashed"}>
          {live
            ? "Active"
            : plan.seat_status === "pending"
              ? "Pending"
              : plan.status === "inactive"
                ? "Inactive"
                : "Not active"}
        </Pill>
        {plan.scope_type === "department" && plan.scope_slug ? (
          <Link
            href={appHref(`/app/department/${plan.scope_slug}`)}
            className="text-xs font-medium text-primary underline-offset-2 hover:underline"
          >
            Manage
          </Link>
        ) : null}
      </div>
    </div>
  );
}

/**
 * "Your plans" — every subscription active on the account (Spore / Lab / Canopy),
 * so a user can see at a glance which plans they hold in total and who pays for each.
 */
export function PlansCard() {
  const { data, isLoading, isError } = useEntitlements();

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Your plans
      </h2>
      <p className="mb-3 text-xs text-[var(--text-secondary)]">
        Every subscription active on your account.
      </p>

      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading your plans…</p>
      ) : isError ? (
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load your plans.</p>
      ) : !data || data.plans.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">
          You&apos;re on the Free plan. Join or activate a Lab or Canopy plan to unlock
          shared intelligence.
        </p>
      ) : (
        <div className="divide-y divide-border">
          {data.plans.map((plan, i) => (
            <PlanRow key={`${plan.scope_type}-${plan.scope_name}-${i}`} plan={plan} />
          ))}
        </div>
      )}
    </Card>
  );
}
