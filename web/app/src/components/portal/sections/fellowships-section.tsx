"use client";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { SparkleIcon } from "@/components/portal/icons";

/**
 * The Fellowships page. Fellowships are matched to a person's stage,
 * eligibility, and timeline — a distinct approach from grants — and that
 * matcher isn't built yet, so this is an honest work-in-progress placeholder.
 * It lives on its own page (split out from Opportunities/Grants) so the two
 * opportunity types don't get confused.
 */
export function FellowshipsSection() {
  return (
    <div>
      <SectionHeader
        title="Fellowships"
        subtitle="Fellowships matched to your stage, eligibility, and timeline."
      />
      <EmptyState
        icon={<SparkleIcon size={26} className="text-accent" />}
        badge="In progress"
        title="Fellowship matching is being designed"
        description="Fellowships are matched to a person's stage, eligibility, and timeline — a distinct approach we're still shaping. They'll appear here once the matcher is ready."
      />
    </div>
  );
}
