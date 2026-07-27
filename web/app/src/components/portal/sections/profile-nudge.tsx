"use client";

import { useState } from "react";

import { Card } from "@/components/portal/primitives/card";
import { MyloGlyph, ArrowRightIcon, CloseIcon } from "@/components/portal/icons";
import { usePortal, type SectionKey } from "@/components/portal/portal-context";
import { useProfile } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";

/**
 * A dismissible nudge card that prompts the user to complete their research
 * profile. Returns null when the profile is already 100% complete, or when the
 * user has dismissed the nudge for this session.
 */
export function ProfileNudge() {
  const [dismissed, setDismissed] = useState(false);
  const { goToSection } = usePortal();
  const profileQuery = useProfile();

  const completeness = computeCompleteness(profileQuery.data);

  if (dismissed) return null;
  if (!profileQuery.isLoading && completeness.percent === 100) return null;

  // First incomplete item label (lowercased) for the detail copy
  const firstNotDone = completeness.items.find((item) => !item.done);
  const nextStep = firstNotDone ? firstNotDone.label.toLowerCase() : "your profile";

  return (
    <Card
      className={[
        "relative p-[22px]",
        "bg-[linear-gradient(135deg,color-mix(in_srgb,var(--primary)_13%,var(--surface)),var(--surface))]",
      ].join(" ")}
    >
      {/* Dismiss button */}
      <button
        type="button"
        aria-label="Dismiss profile nudge"
        onClick={() => setDismissed(true)}
        className={[
          "absolute top-3 right-3",
          "w-7 h-7 rounded-lg border-none bg-transparent",
          "flex items-center justify-center",
          "text-[var(--text-secondary)] cursor-pointer",
          "hover:bg-surface-alt",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        ].join(" ")}
      >
        <CloseIcon size={15} />
      </button>

      {/* Mylo icon block */}
      <div
        className={[
          "w-11 h-11 rounded-xl bg-primary",
          "flex items-center justify-center mb-[14px]",
          "shadow-[0_4px_12px_color-mix(in_srgb,var(--primary)_40%,transparent)]",
        ].join(" ")}
      >
        <MyloGlyph size={24} className="text-[#fffdf8]" />
      </div>

      {/* Title */}
      <p className="m-0 mb-[5px] text-[15px] font-semibold text-[var(--text-primary)]">
        Profile is {completeness.percent}% complete
      </p>

      {/* Detail */}
      <p className="m-0 mb-4 text-[13px] text-[var(--text-secondary)] leading-[1.5]">
        Add {nextStep} so I can find sharper matches.
      </p>

      {/* CTA pill */}
      <button
        type="button"
        onClick={() => goToSection("profile" as SectionKey)}
        className={[
          "inline-flex items-center gap-[7px]",
          "px-4 py-2 rounded-full",
          "bg-primary text-[#fffdf8]",
          "text-sm font-semibold border-none cursor-pointer",
          "hover:bg-brand-primary-hover",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "transition-colors",
        ].join(" ")}
      >
        Grow my profile
        <ArrowRightIcon size={14} />
      </button>
    </Card>
  );
}
