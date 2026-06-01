import type { ReactNode } from "react";

import { features } from "@/data/landing";
import { cn } from "@/lib/utils";

function IconBubble({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function FeatureStrip() {
  return (
    <section className="border-b border-border py-14 sm:py-16" aria-labelledby="features-heading">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <h2
            id="features-heading"
            className="font-display text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl"
          >
            One connected workspace for lab research
          </h2>
          <p className="mt-3 text-base leading-7 text-[var(--text-secondary)]">
            Discover literature, connect knowledge, find grants and fellowships, and guide
            strategy—with explainable outputs your team can review.
          </p>
        </div>

        <div className="mt-10 grid gap-4 rounded-lg border border-border bg-card p-4 shadow-sm sm:grid-cols-2 sm:p-6 lg:grid-cols-3">
          {features.map(({ title, description, icon: Icon }) => (
            <article key={title} className="flex gap-4 rounded-md p-3">
              <IconBubble>
                <Icon aria-hidden className="size-5" />
              </IconBubble>
              <div>
                <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {description}
                </p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
