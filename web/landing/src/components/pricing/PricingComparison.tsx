import { Check, Minus } from "lucide-react";
import { Fragment } from "react";

import type { ComparisonCell } from "@/data/pricingComparison";
import { pricingComparison } from "@/data/pricingComparison";
import { cn } from "@/lib/utils";

function ComparisonCellContent({ cell }: { cell: ComparisonCell }) {
  if (cell.kind === "check") {
    return (
      <span className="inline-flex items-center justify-center text-primary">
        <Check aria-hidden className="size-4" strokeWidth={2.5} />
        <span className="sr-only">Included</span>
      </span>
    );
  }

  if (cell.kind === "cross") {
    return (
      <span className="inline-flex items-center justify-center text-border">
        <Minus aria-hidden className="size-4" strokeWidth={2} />
        <span className="sr-only">Not included</span>
      </span>
    );
  }

  if (cell.kind === "partial") {
    return (
      <span className="text-[11px] italic text-[var(--text-secondary)]">{cell.value}</span>
    );
  }

  return <span className="text-xs text-[var(--text-primary)]">{cell.value}</span>;
}

const planCellKeys = ["spore", "lab", "canopy"] as const;

export function PricingComparison() {
  return (
    <section className="py-12 sm:py-14" aria-labelledby="pricing-comparison-heading">
      <p className="reveal text-xs font-medium uppercase tracking-[0.14em] eyebrow">
        {pricingComparison.eyebrow}
      </p>
      <h2
        id="pricing-comparison-heading"
        className="font-display reveal mt-2 text-[clamp(1.5rem,3.2vw,2rem)] font-medium leading-tight text-[var(--text-primary)]"
      >
        {pricingComparison.title}
      </h2>
      <p className="reveal mt-2 text-sm leading-6 text-[var(--text-secondary)]">
        {pricingComparison.subtitle}
      </p>

      <div className="reveal mt-8 overflow-x-auto rounded-2xl border border-border bg-card">
        <table className="compare-table w-full min-w-[40rem] border-collapse text-[13px]">
          <caption className="sr-only">
            Feature comparison across Spore, Mycelium Lab, and Canopy
          </caption>
          <thead>
            <tr className="border-b border-border/80 bg-[var(--surface-alt)]">
              <th scope="col" className="w-[38%] px-4 py-4 text-left" />
              {pricingComparison.plans.map((plan) => (
                <th
                  key={plan.id}
                  scope="col"
                  className={cn(
                    "px-4 py-4 text-center text-xs font-medium text-[var(--text-secondary)]",
                    "highlighted" in plan && plan.highlighted && "text-primary",
                  )}
                >
                  <div className="flex flex-col items-center gap-1">
                    <span
                      className={cn(
                        "inline-block rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide",
                        plan.pillClass,
                      )}
                    >
                      {plan.name}
                    </span>
                    <span className="font-display text-base font-medium text-[var(--text-primary)]">
                      {plan.price}
                    </span>
                    <span className="text-[10px] text-[var(--text-secondary)]">
                      {plan.priceUnit}
                    </span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pricingComparison.categories.map((category) => (
              <Fragment key={category.title}>
                <tr>
                  <td
                    colSpan={4}
                    className="border-y border-border/80 bg-[var(--surface-alt)] px-4 py-2.5 font-display text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
                  >
                    {category.title}
                  </td>
                </tr>
                {category.rows.map((row) => (
                  <tr
                    key={row.feature}
                    className="compare-row border-b border-divider transition-colors hover:bg-[color-mix(in_srgb,var(--brand-secondary)_8%,transparent)]"
                  >
                    <th scope="row" className="px-4 py-2.5 text-left font-normal">
                      <span className="text-[13px] text-[var(--text-primary)]">{row.feature}</span>
                      {"description" in row && row.description ? (
                        <span className="mt-0.5 block text-[11px] text-[var(--text-secondary)]">
                          {row.description}
                        </span>
                      ) : null}
                    </th>
                    {planCellKeys.map((planKey, index) => (
                      <td
                        key={planKey}
                        className={cn(
                          "px-2 py-2.5 text-center align-middle",
                          index === 1 && "bg-primary/[0.04]",
                        )}
                      >
                        <ComparisonCellContent cell={row[planKey]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-5 text-xs leading-[1.8] text-[var(--text-secondary)]">
        <span className="font-medium text-[var(--text-primary)]">Mycelium Lab</span> requires a
        minimum of 3 members and supports up to 15 members and 5 PIs/Co-PIs. &nbsp;·&nbsp;
        <span className="font-medium text-[var(--text-primary)]">Canopy</span> requires a minimum
        of 15 members with no upper limit. &nbsp;·&nbsp; All prices are billed monthly. Annual
        billing discounts available on request.
      </p>
    </section>
  );
}
