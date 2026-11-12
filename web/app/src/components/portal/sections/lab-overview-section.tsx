"use client";

import * as React from "react";

import { LabChangesCard } from "@/components/portal/ambient/lab-changes-card";
import { usePortal } from "@/components/portal/portal-context";
import { EditIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { LabEditorModal } from "@/components/portal/sections/lab-editor-modal";
import { MyloReportCard } from "@/components/portal/sections/mylo-report-card";
import {
  AnnouncedPanel,
  ClosingSoonPanel,
} from "@/components/portal/sections/announced-panel";
import { MyloFoundCard } from "@/components/portal/sections/mylo-found-card";
import {
  ClosingSoon,
  FoldedReport,
  ForEachPerson,
  OverviewHead,
  ProjectPulse,
  TodayByTheme,
  overviewItems,
} from "@/components/portal/sections/overview-layout";
import { LabEditor } from "@/components/portal/sections/lab-onboarding";
import { AskMyloButton } from "@/components/portal/mylo/ask-button";
import {
  useAnnouncements,
  useLabDailyBriefing,
  useLabProfile,
  useLabRecommendations,
} from "@/lib/portal/hooks";
import type { MyLab } from "@/lib/portal/types";
import { CAPABILITY, can } from "@/lib/portal/capabilities";


/**
 * The lab's front page — the landing view when a lab is the active workspace. It
 * mirrors the personal overview exactly: the greeting, then a two-column layout
 * with the lab's written "Mylo Report" (scrollable) on the left and, on the
 * right, what Mylo found for the lab (today / week / month / year), the top
 * matched papers, and the nearest saved deadlines. When the lab has no profile
 * yet, a manager sees inline onboarding here; a member sees an honest "not set
 * up yet" note.
 */
export function LabOverviewSection({ lab }: { lab: MyLab }) {
  const { scopeLabel } = usePortal();
  const profileQuery = useLabProfile(lab.slug);
  const recQuery = useLabRecommendations(lab.slug);
  const briefingQuery = useLabDailyBriefing(lab.slug);
  const announcementsQuery = useAnnouncements({ lab: lab.slug });
  const [editing, setEditing] = React.useState(false);

  const profile = profileQuery.data;
  const manage = can(lab, CAPABILITY.PROFILE_EDIT);

  const profileEmpty =
    !profileQuery.isLoading &&
    !!profile &&
    !profile.statement &&
    (profile.areas?.length ?? 0) === 0;

  // Onboarding gate: an unconfigured lab either onboards (manager) or explains
  // itself (member).
  if (profileEmpty) {
    if (manage) {
      return (
        <LabEditor lab={lab} onDone={() => profileQuery.refetch()} />
      );
    }
    return (
      <div>
        <OverviewHead subject="the lab's" />
        <Card className="p-6">
          <p className="text-[14px] text-[var(--text-secondary)]">
            This lab hasn&apos;t set up its research profile yet. Once a lab lead
            describes its purpose and focus, Mylo can start surfacing papers,
            grants, and conferences here.
          </p>
        </Card>
      </div>
    );
  }

  const rec = recQuery.data;
  const items = overviewItems({
    papers: rec?.papers,
    grants: rec?.grants,
    fellowships: rec?.fellowships,
    conferences: rec?.conferences,
    recommendedFor: rec?.recommended_for,
  });
  const announcing = Boolean(announcementsQuery.data?.settings.enabled);

  return (
    <div className="ws-overview" data-layout="split">
      <OverviewHead
        subject="the lab's"
        action={
          <>
            <AskMyloButton anchor={{ kind: "lab", key: lab.slug }} title={lab.name} size="head" />
            {manage ? (
              <button type="button" onClick={() => setEditing(true)} className="ws-btn ws-btn-line">
                <EditIcon size={14} />
                Edit lab profile
              </button>
            ) : null}
          </>
        }
      />
      <p className="ws-meta-text ws-overview-scope">You&apos;re viewing {scopeLabel}.</p>

      <div className="ws-split">
        <div className="ws-split-main">
          <FoldedReport>
            <MyloReportCard
              data={briefingQuery.data}
              isLoading={briefingQuery.isLoading}
              title="Lab Mylo Report"
              statsSubject="the lab"
            />
          </FoldedReport>
          <TodayByTheme items={items} isLoading={recQuery.isLoading} />
        </div>

        <div className="ws-split-side">
          {announcing ? (
            <>
              <AnnouncedPanel
                data={announcementsQuery.data}
                isLoading={announcementsQuery.isLoading}
                isError={announcementsQuery.isError}
              />
              {/* The same list Mylo posts in Discord each morning. */}
              <ClosingSoonPanel
                items={announcementsQuery.data?.closing_soon ?? []}
                isLoading={announcementsQuery.isLoading}
                isError={announcementsQuery.isError}
              />
            </>
          ) : (
            <ClosingSoon items={items} isLoading={recQuery.isLoading} />
          )}
          <ForEachPerson items={items} isLoading={recQuery.isLoading} />
          <ProjectPulse />
          <MyloFoundCard windowCounts={rec?.window_counts} isLoading={recQuery.isLoading} />
          <LabChangesCard slug={lab.slug} />
        </div>
      </div>

      {editing ? (
        <LabEditorModal lab={lab} onClose={() => setEditing(false)} />
      ) : null}
    </div>
  );
}
