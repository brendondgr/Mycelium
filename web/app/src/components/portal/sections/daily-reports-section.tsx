"use client";

import * as React from "react";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { ReportIcon } from "@/components/portal/icons";

export function DailyReportsSection() {
  return (
    <div>
      <SectionHeader
        title="Daily Reports"
        subtitle="Your personalized research digest, gathered every morning."
      />
      <EmptyState
        icon={<ReportIcon size={28} />}
        badge="Coming soon"
        title="Your first daily report is on its way"
        description="Once Milo's literature scan runs against your watch topics, your morning digest — new papers with clear why-it-matters context — will appear here."
      />
    </div>
  );
}
