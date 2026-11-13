"use client";

import * as React from "react";

import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import {
  useConferences,
  useDailyBriefing,
  useDailyReport,
  useDeadlines,
  useDepartmentDailyBriefing,
  useDepartmentRecommendations,
  useFellowships,
  useGrants,
  useWindowCounts,
} from "@/lib/portal/hooks";

import { MyloReportCard } from "@/components/portal/sections/mylo-report-card";
import { MyloFoundCard } from "@/components/portal/sections/mylo-found-card";
import { DeadlinesPanel } from "@/components/portal/sections/overview-panels";
import { LabOverviewSection } from "@/components/portal/sections/lab-overview-section";
import { AskMyloButton } from "@/components/portal/mylo/ask-button";
import { GettingStarted, NothingYet, useSetupStatus } from "@/components/portal/sections/getting-started";
import {
  ClosingSoon,
  FoldedReport,
  MyloAsks,
  OverviewHead,
  ProjectPulse,
  TodayByTheme,
  overviewItems,
} from "@/components/portal/sections/overview-layout";

/**
 * The Overview — the landing view of the workspace, in the split layout
 * chosen in `/labs`. The page scrolls as one: the main column holds Mylo's
 * written report and this week's new items grouped by theme across all four
 * feeds; the side column holds what closes soon, Mylo's questions, project
 * pulse, what Mylo found, and the reader's saved deadlines.
 *
 * A new instance has none of that yet. Its administrators get the "Getting
 * started" checklist above everything until its steps are done; anyone else
 * looking at an overview with nothing in it gets a plain explanation instead
 * of a page of zeros.
 */
export function OverviewSection() {
  const { user, scopeLabel, currentLab, currentDepartment } = usePortal();
  const isAdmin = isPlatformAdmin(user);
  const setupQuery = useSetupStatus(isAdmin);
  const personalBriefing = useDailyBriefing();
  // A department works like a lab: its overview reads its own report and its
  // own four feeds, not the reader's personal ones.
  const deptId = !currentLab && currentDepartment ? currentDepartment.id : undefined;
  const deptBriefing = useDepartmentDailyBriefing(deptId);
  const deptRec = useDepartmentRecommendations(deptId);
  const briefingQuery = deptId ? deptBriefing : personalBriefing;
  const windowCountsQuery = useWindowCounts();
  const dailyReportQuery = useDailyReport();
  const deadlinesQuery = useDeadlines();
  const grantsQuery = useGrants();
  const fellowshipsQuery = useFellowships();
  const conferencesQuery = useConferences();

  const items = React.useMemo(
    () =>
      deptId
        ? overviewItems({
            papers: deptRec.data?.papers,
            grants: deptRec.data?.grants,
            fellowships: deptRec.data?.fellowships,
            conferences: deptRec.data?.conferences,
            recommendedFor: deptRec.data?.recommended_for,
          })
        : overviewItems({
            papers: dailyReportQuery.data?.suggestions,
            grants: grantsQuery.data?.items,
            fellowships: fellowshipsQuery.data?.items,
            conferences: conferencesQuery.data?.items,
          }),
    [
      deptId,
      deptRec.data,
      dailyReportQuery.data,
      grantsQuery.data,
      fellowshipsQuery.data,
      conferencesQuery.data,
    ],
  );
  const feedsLoading = deptId
    ? deptRec.isLoading
    : dailyReportQuery.isLoading ||
      grantsQuery.isLoading ||
      fellowshipsQuery.isLoading ||
      conferencesQuery.isLoading;
  const nothingYet =
    !feedsLoading &&
    !briefingQuery.isLoading &&
    items.length === 0 &&
    !(briefingQuery.data?.briefing?.body ?? "").trim();
  // An administrator of an unfinished instance sees the checklist in place of
  // the empty panels; once it is done, the overview is the usual one.
  const checklistOpen = isAdmin && !setupQuery.isError && !setupQuery.data?.complete;

  // When a lab is the active workspace, its overview replaces the personal one.
  if (currentLab) {
    return <LabOverviewSection lab={currentLab} />;
  }

  return (
    <div className="ws-overview" data-layout="split">
      <OverviewHead
        subject={currentDepartment ? "the department's" : "your"}
        action={
          // A department's workspace opens on this overview: ask about the department.
          currentDepartment ? (
            <AskMyloButton
              anchor={{ kind: "department", key: currentDepartment.id }}
              title={currentDepartment.name}
              size="head"
            />
          ) : null
        }
      />
      <p className="ws-meta-text ws-overview-scope">You&apos;re viewing {scopeLabel}.</p>
      {isAdmin ? (
        <div className="mb-[var(--d-section,24px)]">
          <GettingStarted enabled />
        </div>
      ) : null}
      {nothingYet && !isAdmin ? (
        <NothingYet />
      ) : nothingYet && checklistOpen ? null : (
      <div className="ws-split">
        <div className="ws-split-main">
          <FoldedReport>
            {deptId ? (
              <MyloReportCard
                data={briefingQuery.data}
                isLoading={briefingQuery.isLoading}
                title="Department Mylo Report"
                statsSubject="the department"
              />
            ) : (
              <MyloReportCard data={briefingQuery.data} isLoading={briefingQuery.isLoading} />
            )}
          </FoldedReport>
          <TodayByTheme items={items} isLoading={feedsLoading} />
        </div>
        <div className="ws-split-side">
          <ClosingSoon items={items} isLoading={feedsLoading} />
          <MyloAsks />
          <ProjectPulse />
          <MyloFoundCard
            windowCounts={windowCountsQuery.data?.window_counts}
            isLoading={windowCountsQuery.isLoading}
          />
          <DeadlinesPanel items={deadlinesQuery.data?.items ?? []} isLoading={deadlinesQuery.isLoading} />
        </div>
      </div>
      )}
    </div>
  );
}
