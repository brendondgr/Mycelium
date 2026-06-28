"use client";

import { MyloMark } from "@/components/brand/mylo-mark";
import { cn } from "@/lib/utils";

export type SynthesisStage = {
  /** Short, present-tense description of the work Mylo is doing. */
  label: string;
};

export type ProfileSynthesisProgressProps = {
  /** The ordered stages Mylo moves through while building the profile. */
  stages: SynthesisStage[];
  /**
   * Index of the stage currently in progress. Stages before it are complete;
   * stages after it are pending.
   */
  active: number;
  /** When true, every stage is shown complete and the success line appears. */
  done: boolean;
};

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" aria-hidden="true">
      <path
        d="M5 10.5 8.5 14 15 6.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// A narrated wait while the language model synthesizes the research profile.
// The stage list mirrors the real backend pipeline; the active stage pulses and
// completed stages settle to a check, so the user can see the work happening
// rather than staring at a frozen button.
export default function ProfileSynthesisProgress({
  stages,
  active,
  done,
}: ProfileSynthesisProgressProps) {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center text-center">
      <div className="relative h-[150px] w-[200px]">
        <svg viewBox="0 0 200 150" className="absolute inset-0 h-full w-full">
          <g stroke="var(--brand-secondary)" strokeWidth="1.6" fill="none">
            <path d="M100 84 L44 40" />
            <path d="M100 84 L160 44" />
            <path d="M100 84 L100 22" />
          </g>
          <g>
            <circle
              cx="44"
              cy="40"
              r="5"
              fill="var(--primary)"
              className="motion-safe:animate-pulse"
            />
            <circle
              cx="160"
              cy="44"
              r="5"
              fill="var(--brand-accent)"
              className="motion-safe:animate-pulse"
            />
            <circle
              cx="100"
              cy="22"
              r="5"
              fill="var(--brand-secondary)"
              className="motion-safe:animate-pulse"
            />
          </g>
        </svg>
        <div className="absolute left-1/2 top-[58%] h-[64px] w-[58px] -translate-x-1/2 -translate-y-1/2">
          <MyloMark className="mylo-float h-full w-full" />
        </div>
      </div>

      <h2 className="mt-1 font-serif text-2xl font-semibold text-[var(--text-primary)]">
        {done ? "Your profile is ready" : "Mylo is building your profile…"}
      </h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        {done
          ? "Bringing you to your draft to review."
          : "Reading your work and weaving it into a research profile."}
      </p>

      <ol className="mt-6 w-full space-y-1 text-left" aria-live="polite">
        {stages.map((stage, index) => {
          const complete = done || index < active;
          const current = !done && index === active;
          return (
            <li
              key={stage.label}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors",
                current ? "bg-secondary/60" : "bg-transparent",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 flex-none items-center justify-center rounded-full border transition-colors",
                  complete
                    ? "border-primary bg-primary text-primary-foreground"
                    : current
                      ? "border-primary text-primary"
                      : "border-border text-[var(--text-muted)]",
                )}
                aria-hidden="true"
              >
                {complete ? (
                  <CheckIcon />
                ) : current ? (
                  <span className="h-2 w-2 rounded-full bg-primary motion-safe:animate-ping" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>
              <span
                className={cn(
                  "text-sm",
                  complete
                    ? "text-[var(--text-secondary)]"
                    : current
                      ? "font-medium text-[var(--text-primary)]"
                      : "text-[var(--text-muted)]",
                )}
              >
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
