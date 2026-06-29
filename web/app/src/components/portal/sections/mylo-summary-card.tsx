"use client";

import { Card } from "@/components/portal/primitives/card";
import { useProfile, useWatch } from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";

/**
 * Mylo's weekly summary card. The headline is always honest about whether a
 * full scan has run yet — it never fabricates paper or grant counts.
 */
export function MyloSummaryCard() {
  const profileQuery = useProfile();
  const watchQuery = useWatch();

  const completeness = computeCompleteness(profileQuery.data);
  const watch = watchQuery.data;

  // Headline: setup-aware, never fakes results
  let headline: string;
  if (profileQuery.isLoading) {
    headline = "Loading your research profile…";
  } else if (completeness.percent < 100) {
    headline =
      "Your research radar is taking shape — finishing your profile lets me find sharper matches.";
  } else {
    headline =
      "Your radar is set. I'll surface papers, grants, and fellowships here as soon as your first scan runs.";
  }

  // Detail paragraph: mention watch topics / cadence when available
  let detail: string;
  if (watchQuery.isLoading || profileQuery.isLoading) {
    detail = "Loading your watch preferences…";
  } else if (watch && watch.topics.length > 0) {
    const topicCount = watch.topics.length;
    const cadenceLabel =
      watch.cadence === "realtime"
        ? "real-time"
        : watch.cadence === "daily"
          ? "daily"
          : "weekly";
    detail = `I'm watching ${topicCount} topic${topicCount === 1 ? "" : "s"} across literature databases and funding sources. You're set to receive a ${cadenceLabel} digest — I'll flag new papers, open grants, and fellowships that match your interests.`;
  } else if (completeness.percent === 100) {
    detail =
      "Head over to Goals to add watch topics so Mylo knows which research areas to monitor for you.";
  } else {
    detail =
      "Once your profile and watch topics are in place, I'll monitor literature databases and funding sources on your behalf — surfacing anything worth your attention.";
  }

  return (
    <Card accent="primary-rule" className="p-6">
      {/* Eyebrow */}
      <div className="flex items-center gap-2 mb-[9px]">
        <span className="text-[10.5px] font-semibold tracking-[.09em] uppercase text-primary">
          Mylo · this week
        </span>
      </div>

      {/* Headline */}
      <p className="font-serif text-[22px] font-medium leading-[1.34] tracking-[-0.01em] text-[var(--text-primary)] [text-wrap:pretty] mb-2">
        {headline}
      </p>

      {/* Detail */}
      <p className="text-[14.5px] text-[var(--text-secondary)] leading-[1.55] max-w-[70ch] [text-wrap:pretty] m-0">
        {detail}
      </p>
    </Card>
  );
}
