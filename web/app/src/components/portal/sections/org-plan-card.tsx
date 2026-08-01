"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { Pill } from "@/components/portal/primitives/pill";
import {
  useActivateDeptBilling,
  useActivateLabBilling,
  useDeptBilling,
  useLabBilling,
} from "@/lib/portal/hooks";
import type { OrgBilling } from "@/lib/portal/types";

const TIER_LABEL: Record<string, string> = {
  lab: "Mycelium Lab",
  canopy: "Canopy",
};

function usd(cents: number): string {
  return (cents / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * A price on a plan. On a complimentary plan the list price is struck through with
 * "Free" beside it, so the value of what was granted stays visible rather than being
 * quietly replaced by a zero. `<s>` carries the meaning for screen readers too.
 */
function Price({ cents, comped }: { cents: number; comped: boolean }) {
  if (!comped) return <>{usd(cents)}</>;
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <s className="text-[var(--text-muted)]">{usd(cents)}</s>
      <span className="text-primary">Free</span>
    </span>
  );
}

/** Shared body for a lab / department plan card, given resolved billing state. */
function PlanBody({
  billing,
  isLoading,
  isError,
  onActivate,
  activating,
  activateError,
}: {
  billing: OrgBilling | undefined;
  isLoading: boolean;
  isError: boolean;
  onActivate: () => void;
  activating: boolean;
  activateError: string | null;
}) {
  if (isLoading) {
    return <p className="text-sm text-[var(--text-secondary)]">Loading the plan…</p>;
  }
  if (isError || !billing) {
    return <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load the plan.</p>;
  }

  const tierLabel = billing.tier ? (TIER_LABEL[billing.tier] ?? billing.tier) : "—";
  const perSeat = usd(billing.seat_price_cents);
  const comped = billing.is_comped;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {tierLabel}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          {comped ? <Pill tone="accent">Complimentary</Pill> : null}
          <Pill tone={billing.is_active ? "primary" : "dashed"}>
            {billing.is_active ? "Active" : "Inactive"}
          </Pill>
        </div>
      </div>

      {billing.is_active ? (
        <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
          <dt className="text-[var(--text-secondary)]">Seats</dt>
          <dd className="text-right font-medium text-[var(--text-primary)]">
            {billing.seat_count}
          </dd>
          <dt className="text-[var(--text-secondary)]">Per seat / mo</dt>
          <dd className="text-right font-medium text-[var(--text-primary)]">
            <Price cents={billing.seat_price_cents} comped={comped} />
          </dd>
          <dt className="text-[var(--text-secondary)]">Monthly total</dt>
          <dd className="text-right font-semibold text-[var(--text-primary)]">
            {/* A comped plan bills zero, so strike the list total it *would* have
                cost — striking the zero itself would say nothing. */}
            <Price
              cents={
                comped
                  ? billing.seat_count * billing.seat_price_cents
                  : billing.recurring_monthly_cents
              }
              comped={comped}
            />
          </dd>
          <dt className="text-[var(--text-secondary)]">Mylo on Discord</dt>
          <dd className="text-right font-medium text-[var(--text-primary)]">
            {billing.mylo_included ? "Included" : "Not included"}
          </dd>
          {comped ? null : billing.current_period_end ? (
            <>
              <dt className="text-[var(--text-secondary)]">Renews</dt>
              <dd className="text-right text-[var(--text-secondary)]">
                {billing.current_period_end}
              </dd>
            </>
          ) : null}
          {billing.expires_at ? (
            <>
              <dt className="text-[var(--text-secondary)]">Plan ends</dt>
              <dd className="text-right text-[var(--text-secondary)]">
                {formatDate(billing.expires_at)}
              </dd>
            </>
          ) : null}
        </dl>
      ) : (
        <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
          The structure is free. Activate the plan to unlock shared intelligence for
          everyone — billed at {perSeat} per member per month once active.
        </p>
      )}

      {comped && billing.is_active ? (
        <p className="text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
          This plan was granted with no end date, so nothing is billed. Every member
          keeps the full {tierLabel} entitlement.
        </p>
      ) : null}

      {billing.can_manage && !billing.is_active ? (
        <button
          type="button"
          onClick={onActivate}
          disabled={activating}
          className="inline-flex items-center justify-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {activating ? "Activating…" : "Activate plan"}
        </button>
      ) : null}

      {activateError ? (
        <p className="text-[12.5px] text-clay" role="alert">
          {activateError}
        </p>
      ) : null}
    </div>
  );
}

/** A lab's plan state + a manager Activate action (F-3). */
export function LabPlanCard({ slug }: { slug: string }) {
  const { data, isLoading, isError } = useLabBilling(slug);
  const activate = useActivateLabBilling(slug);
  const [error, setError] = React.useState<string | null>(null);

  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Lab plan
      </h3>
      <PlanBody
        billing={data}
        isLoading={isLoading}
        isError={isError}
        activating={activate.isPending}
        activateError={error}
        onActivate={() => {
          setError(null);
          activate.mutate(undefined, {
            onError: (e) => setError((e as Error).message),
          });
        }}
      />
    </Card>
  );
}

/** A department's plan state + a head Activate action. */
export function DeptPlanCard({ deptId }: { deptId: string }) {
  const { data, isLoading, isError } = useDeptBilling(deptId);
  const activate = useActivateDeptBilling(deptId);
  const [error, setError] = React.useState<string | null>(null);

  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Department plan
      </h3>
      <PlanBody
        billing={data}
        isLoading={isLoading}
        isError={isError}
        activating={activate.isPending}
        activateError={error}
        onActivate={() => {
          setError(null);
          activate.mutate(undefined, {
            onError: (e) => setError((e as Error).message),
          });
        }}
      />
    </Card>
  );
}
