import type { ReactNode } from "react";
import { Leaf } from "lucide-react";

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
    <section
      className="relative isolate overflow-hidden border-b border-border py-12 sm:py-14 lg:py-16"
      aria-labelledby="features-heading"
    >
      <img
        src="/images/connected-workspace-1600.webp"
        srcSet="/images/connected-workspace-900.webp 900w, /images/connected-workspace-1600.webp 1600w"
        sizes="100vw"
        alt=""
        aria-hidden="true"
        className="absolute inset-0 -z-20 h-full w-full object-cover object-center"
        width="1600"
        height="686"
        loading="lazy"
        decoding="async"
      />
      <div className="absolute inset-0 -z-10 bg-[#f8f4ec]/76 backdrop-blur-[1px] lg:bg-[#f8f4ec]/60" />

      <div className="mx-auto grid w-full max-w-[94rem] gap-8 px-4 sm:px-6 md:px-8 lg:grid-cols-[0.86fr_1.18fr] lg:gap-10 lg:px-10 xl:gap-12 xl:px-12">
        <div
          className="mx-auto flex max-w-[30rem] flex-col items-center text-center"
          data-reveal-group
          data-reveal-step="90"
        >
          <div className="reveal inline-flex min-h-9 items-center gap-2 rounded-full border border-primary/30 bg-[#f6f8e7]/80 px-4 text-xs font-bold uppercase text-[#3f5f2e] shadow-sm backdrop-blur-sm">
            <Leaf aria-hidden className="size-3.5" />
            <span>Mycelium</span>
          </div>

          <h2
            id="features-heading"
            className="font-display reveal mt-6 max-w-[27rem] text-[clamp(2rem,7.2vw,2.75rem)] font-medium leading-[1.02] text-[#1f2b1d] sm:text-[clamp(2.35rem,4.2vw,3.25rem)] lg:text-[clamp(2.5rem,3.55vw,3.5rem)]"
          >
            One <span className="italic text-[#3f6e34]">connected</span>
            <span className="block">workspace for</span>
            <span className="block">lab research</span>
          </h2>

          <div className="reveal mt-6 flex w-full max-w-[14rem] items-center gap-3" aria-hidden="true">
            <span className="h-px flex-1 bg-[#cdae6b]" />
            <Leaf className="size-4 text-[#c9a35a]" />
            <span className="h-px flex-1 bg-[#cdae6b]" />
          </div>

          <p className="reveal mt-6 max-w-[25rem] text-base leading-7 text-[#314333]">
            Discover literature, connect knowledge, find grants and fellowships, and guide
            strategy—with explainable outputs your team can review.
          </p>

          <div className="reveal mt-8 inline-flex max-w-full items-center gap-3 rounded-full border border-[#776538]/15 bg-[#fcf9eb]/85 py-2.5 pl-2.5 pr-4 text-sm leading-6 text-[#40503a] shadow-[0_10px_24px_rgb(70_52_24/7%)] backdrop-blur-sm sm:mt-12">
            <IconBubble className="size-10 bg-primary/15">
              <Leaf aria-hidden className="size-4" />
            </IconBubble>
            <span>
              Built for researchers, grounded in <strong className="font-semibold">trust.</strong>
            </span>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:gap-6 xl:gap-9" data-reveal-group data-reveal-step="90">
          {features.map(({ title, description, icon: Icon }) => (
            <article
              key={title}
              className="reveal grid min-h-[9.25rem] grid-cols-[2.75rem_1fr] items-center gap-3.5 rounded-2xl border border-[#7d6237]/18 bg-card/90 p-4 shadow-[0_14px_34px_rgb(52_39_20/7%)] backdrop-blur-md sm:grid-cols-[3.25rem_1fr] sm:p-5"
            >
              <IconBubble className="size-11 sm:size-12">
                <Icon aria-hidden className="size-5" />
              </IconBubble>
              <div>
                <h3 className="text-base font-bold leading-tight text-[#151f16] sm:text-lg">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-[#324335]">
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
