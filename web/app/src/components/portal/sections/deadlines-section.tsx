"use client";

import * as React from "react";

import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CalendarIcon } from "@/components/portal/icons";

export function DeadlinesSection() {
  return (
    <div>
      <SectionHeader
        title="Deadlines & readiness"
        subtitle="Upcoming dates and how prepared each submission is."
      />
      <EmptyState
        icon={<CalendarIcon size={28} />}
        title="No deadlines tracked yet"
        description="As Milo matches opportunities to your work, their deadlines and a proposal-readiness checklist will collect here."
      />
    </div>
  );
}
