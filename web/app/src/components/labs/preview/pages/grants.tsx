"use client";

import * as React from "react";

import type { OptionValue } from "@/components/labs/schema";
import { GRANTS, type Grant } from "@/components/labs/preview/fixtures";
import { GrantItem, PageHead, usePreview } from "@/components/labs/preview/parts";

const HORIZON = 90;

/**
 * The next ninety days as one line, each open call a mark at the day it
 * closes. A real timeline: position carries the date, the label carries it
 * again in words, so nothing depends on reading the axis alone.
 */
function Horizon({ grants }: { grants: Grant[] }) {
  const { open } = usePreview();
  return (
    <section className="lx-horizon lx-panel-box lx-rise" aria-label="Deadlines over the next 90 days">
      <div className="lx-horizon-track">
        <span className="lx-horizon-today">Today</span>
        <span className="lx-horizon-end">90 days</span>
        {grants
          .filter((g) => g.closesIn <= HORIZON)
          .map((g, i) => (
            <button
              key={g.id}
              type="button"
              className="lx-horizon-mark"
              data-soon={g.closesIn <= 14 || undefined}
              data-row={i % 2}
              data-align={g.closesIn / HORIZON > 0.7 ? "end" : "start"}
              style={{ left: `${(g.closesIn / HORIZON) * 100}%` }}
              onClick={() => open({ kind: "grant", item: g })}
            >
              <span className="lx-horizon-dot" aria-hidden="true" />
              <span className="lx-horizon-label">
                {g.closesOn} · {g.funder.split(" · ")[0]}
              </span>
            </button>
          ))}
      </div>
    </section>
  );
}

export function GrantsPage({ o }: { o: Record<string, OptionValue> }) {
  const layout = o.layout as string;
  const itemProps = {
    deadline: o.deadline as string,
    eligibility: Boolean(o.eligibility),
    amount: Boolean(o.amount),
  };
  const sorted = [...GRANTS].sort((a, b) => a.closesIn - b.closesIn);

  return (
    <div className="lx-grants">
      <PageHead
        title="Grants"
        lede={
          <>
            Open calls that fit the lab&apos;s themes. <strong className="lx-gold">One closes within two weeks.</strong>
          </>
        }
      />

      {layout === "timeline" ? (
        <>
          <Horizon grants={sorted} />
          {Array.from(new Set(sorted.map((g) => g.month))).map((month) => (
            <section key={month} className="lx-feed-group" aria-label={`Closing in ${month}`}>
              <h2 className="lx-group-label">Closing in {month}</h2>
              <div className="lx-feed-items">
                {sorted
                  .filter((g) => g.month === month)
                  .map((g) => (
                    <GrantItem key={g.id} grant={g} {...itemProps} />
                  ))}
              </div>
            </section>
          ))}
        </>
      ) : layout === "board" ? (
        <div className="lx-board">
          {(
            [
              ["new", "New"],
              ["closing", "Closing soon"],
              ["saved", "Saved"],
            ] as const
          ).map(([status, label]) => {
            const items = sorted.filter((g) => g.status === status);
            return (
              <section key={status} className="lx-board-col" aria-label={label}>
                <h2 className="lx-group-label">
                  {label} <span className="lx-count">{items.length}</span>
                </h2>
                <div className="lx-feed-items">
                  {items.map((g) => (
                    <GrantItem key={g.id} grant={g} {...itemProps} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div className="lx-feed-items">
          {sorted.map((g) => (
            <GrantItem key={g.id} grant={g} {...itemProps} />
          ))}
        </div>
      )}
    </div>
  );
}
