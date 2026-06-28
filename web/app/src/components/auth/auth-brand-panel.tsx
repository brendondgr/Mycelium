import * as React from "react";

import { MyloMark } from "@/components/brand/mylo-mark";
import { cn } from "@/lib/utils";

function MyceliumBackdrop() {
  return (
    <svg
      viewBox="0 0 600 800"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.16]"
    >
      <g stroke="var(--brand-accent)" strokeWidth="1.1" fill="none">
        <path d="M-20 560 C140 520 200 640 360 600 C520 560 560 660 700 620" />
        <path d="M-20 640 C120 610 220 700 380 660 C520 626 600 700 700 680" />
        <path d="M80 800 C120 660 60 600 140 500 C210 412 160 320 240 240" />
        <path d="M460 800 C420 660 500 600 440 500 C380 412 460 320 380 240" />
      </g>
      <g fill="var(--brand-secondary)">
        <circle cx="140" cy="500" r="3.5" />
        <circle cx="360" cy="600" r="3.5" />
        <circle cx="240" cy="240" r="3.5" />
        <circle cx="440" cy="500" r="3.5" />
        <circle cx="380" cy="240" r="3.5" />
      </g>
    </svg>
  );
}

/**
 * The forest-green brand panel shown beside the auth forms (hidden on narrow
 * screens). Caller supplies the headline, blurb, and an optional content slot
 * (quote list, checklist, etc.).
 */
export function AuthBrandPanel({
  heading,
  description,
  children,
  className,
}: {
  heading: React.ReactNode;
  description: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <aside
      className={cn(
        "relative hidden flex-col justify-between overflow-hidden bg-brand-panel px-12 py-14 text-brand-panel-foreground min-[880px]:flex min-[880px]:w-[46%] min-[880px]:max-w-[600px]",
        className,
      )}
    >
      <MyceliumBackdrop />

      <div className="relative flex items-center gap-3">
        <MyloMark className="h-8 w-7" />
        <span className="font-serif text-xl font-semibold tracking-tight">
          Mycelium
        </span>
      </div>

      <div className="relative max-w-md">
        <MyloMark className="mylo-float mb-6 h-28 w-24" />
        <h1 className="font-serif text-4xl font-semibold leading-[1.1]">
          {heading}
        </h1>
        <p className="mt-4 text-base leading-relaxed text-brand-panel-foreground/80">
          {description}
        </p>
        {children ? <div className="mt-7">{children}</div> : null}
      </div>

      <p className="relative text-xs text-brand-panel-foreground/60">
        Trusted by researchers, labs, and departments.
      </p>
    </aside>
  );
}
