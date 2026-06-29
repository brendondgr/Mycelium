"use client";

import * as React from "react";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { SparkleIcon } from "@/components/portal/icons";

export function OpportunitiesSection() {
  return (
    <div>
      <SectionHeader
        title="Opportunities"
        subtitle="Grants and fellowships matched to your profile and timeline."
      />
      <EmptyState
        icon={<SparkleIcon size={28} className="text-accent" />}
        badge="Coming soon"
        title="Opportunity matching is coming"
        description="When scoring is live, Milo will surface grants and fellowships ranked by fit, eligibility, and deadline — each with a plain-language reason it matches your lab."
      />
    </div>
  );
}
