import { Check } from "lucide-react";
import { Fragment } from "react";

import type { ComparisonCell } from "@/data/pricingComparison";
import { pricingComparison } from "@/data/pricingComparison";
import { cn } from "@/lib/utils";

function ComparisonCellContent({ cell }: { cell: ComparisonCell }) {
  if (cell.kind === "included") {
    return (
      <span className="inline-flex items-center justify-center">
        <Check aria-hidden className="size-4 text-primary" strokeWidth={2.5} />
        <span className="sr-only">Included</span>
      </span>
    );
  }

  return (
    <span
      className={cn(
        "text-sm text-[var(--text-secondary)]",
        cell.italic && "italic text-muted-foreground",
      )}
    >
      {cell.value}
    </span>
  );
}

export function PricingComparison() {
  return (
    <section className="mt-16 sm:mt-20" aria-labelledby="pricing-comparison-heading">
      <div className="mx-auto max-w-3xl text-center">
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-primary">
          {pricingComparison.eyebrow}
        </p>
        <h2
          id="pricing-comparison-heading"
          className="font-display mt-3 text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl"
        >
          {pricingComparison.title}
        </h2>
        <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)] sm:text-base">
          {pricingComparison.subtitle}
        </p>
      </div>

      <div className="mt-10 overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
        <table className="w-full min-w-[44rem] border-collapse text-left">
          <caption className="sr-only">Feature comparison across Spore, Mycelium Lab, and Canopy</caption>
          <thead>
            <tr className="border-b border-border">
              <th
                scope="col"
                className="w-[34%] px-4 py-5 text-left sm:px-6"
              />
              {pricingComparison.plans.map((plan) => (
                <th
                  key={plan.id}
                  scope="col"
                  className="px-3 py-5 text-center sm:px-4"
                >
                  <div className="inline-flex flex-col items-center gap-2">
                    <span className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-primary">
                      {plan.name}
                    </span>
                    <span className="text-sm text-[var(--text-secondary)]">{plan.price}</span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pricingComparison.categories.map((category) => (
              <Fragment key={category.title}>
                <tr className="border-b border-border bg-surface-alt/70">
                  <th
                    colSpan={4}
                    scope="colgroup"
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground sm:px-6"
                  >
                    {category.title}
                  </th>
                </tr>
                {category.rows.map((row) => (
                  <tr
                    key={row.feature}
                    className="border-b border-border last:border-b-0 even:bg-[color-mix(in_srgb,var(--surface-alt)_35%,transparent)]"
                  >
                    <th scope="row" className="px-4 py-4 align-top font-normal sm:px-6">
                      <div className="pr-4">
                        <p className="text-sm font-medium text-[var(--text-primary)]">{row.feature}</p>
                        {"description" in row && row.description ? (
                          <p className="mt-1 text-xs leading-5 text-muted-foreground">
                            {row.description}
                          </p>
                        ) : null}
                      </div>
                    </th>
                    <td className="px-3 py-4 text-center align-middle sm:px-4">
                      <ComparisonCellContent cell={row.spore} />
                    </td>
                    <td className="px-3 py-4 text-center align-middle sm:px-4">
                      <ComparisonCellContent cell={row.lab} />
                    </td>
                    <td className="px-3 py-4 text-center align-middle sm:px-4">
                      <ComparisonCellContent cell={row.canopy} />
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-6 text-center text-xs leading-6 text-muted-foreground sm:text-sm">
        {pricingComparison.footnote}
      </p>
    </section>
  );
}
