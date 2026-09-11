"use client";

import * as React from "react";

import { useQueryClient } from "@tanstack/react-query";

import { ClusterOrganizer } from "@/components/onboarding/cluster-organizer";
import { Chip, TokenField, dedupe, inputClass } from "@/components/onboarding/fields";
import {
  EditorField,
  EditorModal,
  EditorSection,
  EditorToggleRow,
  type EditorTab,
} from "@/components/portal/primitives/editor-modal";
import {
  confirmInterests,
  saveProfileBasics,
  saveWatch,
} from "@/lib/auth-client";
import { useEntitlements, useProfile, useWatch } from "@/lib/portal/hooks";
import type {
  ClusterGroup,
  ProfileEligibility,
  ResearchInterests,
  WatchCadence,
} from "@/lib/auth-types";
import { cn } from "@/lib/utils";

/** Which panel the modal opens on — callers deep-link from the matching card. */
export type ProfileEditorTab =
  | "about"
  | "focus"
  | "interests"
  | "watch"
  | "delivery"
  | "eligibility";

/**
 * The zones offered in the picker. Deliberately short: these are the zones this
 * product's readers are actually in, and a 400-entry IANA list is a worse control
 * than five right answers plus whatever the account already has. The backend
 * validates any zone name, so nothing here is a ceiling.
 */
const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Tokyo",
  "Australia/Sydney",
  "UTC",
];

/** Local hours a send can target. Day-granular, like the reminder scheduler. */
const SEND_HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function hourLabel(hour: number): string {
  const suffix = hour < 12 ? "am" : "pm";
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}:00 ${suffix}`;
}

const ROLES = [
  { label: "Student", value: "student" },
  { label: "Postdoc", value: "postdoc" },
  { label: "Researcher", value: "researcher" },
  { label: "Principal Investigator", value: "pi" },
  { label: "Staff Scientist", value: "staff" },
];

// Kept in step with the onboarding flow's list — the same preference row is
// written by both surfaces, so a key here that the flow doesn't know would be
// silently dropped the next time someone walked through onboarding.
const WATCH_CATEGORIES = [
  { key: "papers", label: "New papers & preprints", desc: "Relevant to your areas and keywords." },
  { key: "grants", label: "Grant deadlines", desc: "Funding that fits your profile." },
  { key: "fellowships", label: "Fellowships", desc: "Matched to your stage and timeline." },
  { key: "conferences", label: "Conferences & CFPs", desc: "Meetings and calls for papers in your field." },
  { key: "collaborators", label: "Potential collaborators", desc: "People on adjacent problems." },
  { key: "retractions", label: "Retractions & corrections", desc: "When work you cited changes." },
  { key: "graph", label: "Knowledge-graph updates", desc: "New connections across your network." },
];

const CADENCES: { id: WatchCadence; label: string }[] = [
  { id: "daily", label: "Daily digest" },
  { id: "weekly", label: "Weekly digest" },
];

const CITIZENSHIP_OPTIONS: { value: ProfileEligibility["citizenship"]; label: string }[] = [
  { value: "us", label: "US citizen / permanent resident" },
  { value: "international", label: "International student" },
];

const STAGE_OPTIONS: { value: ProfileEligibility["stage"]; label: string }[] = [
  { value: "masters", label: "Master's" },
  { value: "doctoral_early", label: "Early doctoral" },
  { value: "doctoral_dissertation", label: "Dissertation research / write-up" },
  { value: "postdoc", label: "Postdoc / beyond" },
  { value: "", label: "Not applicable" },
];

const FIELD_OPTIONS = [
  "Social Sciences",
  "Sciences/Engineering/Math",
  "Professional Programs",
  "Fine Arts",
  "Humanities",
];

const RESTRICTION_OPTIONS = ["Women", "Equity"];

/**
 * Edit the whole personal profile in one dialog.
 *
 * This replaces "Edit profile" sending the user back through `/app/onboarding`.
 * Onboarding is a first-run narrative — verify your email, import your work,
 * review, one step at a time — and re-entering it to change a cadence made the
 * user re-walk a story they had already finished. Here every field the flow
 * writes is on one surface, split into tabs, saved in one action.
 *
 * The three writes go out **in sequence**, not concurrently: each of the profile
 * endpoints updates its own columns, and issuing them together is what once let a
 * later full-row write clobber an earlier one's result.
 */
export function ProfileEditorModal({
  open,
  initialTab = "focus",
  onClose,
}: {
  open: boolean;
  initialTab?: ProfileEditorTab;
  onClose: () => void;
}) {
  const profileQuery = useProfile();
  const watchQuery = useWatch();

  if (!open) {
    return null;
  }

  // Both reads are already warm from the profile page behind the dialog; this
  // only shows on a cold deep-link.
  if (profileQuery.isLoading || watchQuery.isLoading) {
    return (
      <EditorModal
        eyebrow="Your profile"
        title="Edit profile"
        tabs={[
          {
            id: "loading",
            label: "Loading",
            content: (
              <div className="h-40 animate-pulse rounded-xl bg-surface-alt" />
            ),
          },
        ]}
        activeTab="loading"
        onTabChange={() => {}}
        onClose={onClose}
        onSave={() => {}}
        saveDisabledReason="Loading your profile…"
      />
    );
  }

  return (
    <ProfileEditorForm
      initialTab={initialTab}
      profile={profileQuery.data}
      watch={watchQuery.data}
      onClose={onClose}
    />
  );
}

type LoadedProfile = NonNullable<ReturnType<typeof useProfile>["data"]>;
type LoadedWatch = NonNullable<ReturnType<typeof useWatch>["data"]>;

function ProfileEditorForm({
  initialTab,
  profile,
  watch,
  onClose,
}: {
  initialTab: ProfileEditorTab;
  profile: LoadedProfile | undefined;
  watch: LoadedWatch | undefined;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: entitlements } = useEntitlements();
  const clusterCap = entitlements?.cluster_cap ?? 3;
  const clusterTopicCap = entitlements?.cluster_topic_cap ?? 2;
  const topicCap = entitlements?.topic_cap ?? 6;

  const interests = profile?.interests;

  const [tab, setTab] = React.useState<ProfileEditorTab>(initialTab);
  const [role, setRole] = React.useState(
    ROLES.some((option) => option.value === profile?.academic_title)
      ? (profile?.academic_title as string)
      : "researcher",
  );
  const [institution, setInstitution] = React.useState(profile?.institution ?? "");

  const [statement, setStatement] = React.useState(interests?.statement ?? "");
  const [areas, setAreas] = React.useState<string[]>(interests?.areas ?? []);
  const [keywords, setKeywords] = React.useState<string[]>(
    interests?.keywords ?? [],
  );
  const [skills, setSkills] = React.useState<string[]>(interests?.skills ?? []);
  // Saved clusters load as-is: a plan downgrade must never silently destroy an
  // existing grouping. The organizer still blocks *new* over-cap edits.
  const [clusters, setClusters] = React.useState<ClusterGroup[]>(
    interests?.clusters ?? [],
  );

  const [watchTopics, setWatchTopics] = React.useState<string[]>(
    watch?.topics ?? [],
  );
  const [watchCats, setWatchCats] = React.useState<Record<string, boolean>>(() =>
    WATCH_CATEGORIES.reduce<Record<string, boolean>>((acc, category) => {
      acc[category.key] = (watch?.categories ?? []).includes(category.key);
      return acc;
    }, {}),
  );
  const [cadence, setCadence] = React.useState<WatchCadence>(
    watch?.cadence ?? "daily",
  );
  const [sendHour, setSendHour] = React.useState<number>(
    watch?.send_hour_local ?? 8,
  );
  const [zone, setZone] = React.useState<string>(
    watch?.timezone ?? "America/New_York",
  );
  const [urgentAlerts, setUrgentAlerts] = React.useState<boolean>(
    watch?.urgent_alerts ?? false,
  );
  const [bufferDays, setBufferDays] = React.useState<number>(
    watch?.deadline_buffer_days ?? 14,
  );
  const [windowDays, setWindowDays] = React.useState<number>(
    watch?.min_paper_window_days ?? 60,
  );

  const eligibility = interests?.eligibility;
  const [eligCitizenship, setEligCitizenship] = React.useState<
    ProfileEligibility["citizenship"]
  >(eligibility?.citizenship ?? "us");
  const [eligStage, setEligStage] = React.useState<ProfileEligibility["stage"]>(
    eligibility?.stage ?? "",
  );
  const [eligFields, setEligFields] = React.useState<string[]>(
    eligibility?.fields ?? [],
  );
  const [eligRestrictions, setEligRestrictions] = React.useState<string[]>(
    eligibility?.eligible_restrictions ?? [],
  );
  const [eligLabVisible, setEligLabVisible] = React.useState(
    eligibility?.lab_visible ?? false,
  );

  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setError(null);
    setSaving(true);

    const cleanAreas = dedupe(areas);
    const nextInterests: ResearchInterests = { version: 2, areas: cleanAreas };

    // The interests contract requires that IF `clusters` is present, every area
    // sits in exactly one cluster. Sanitize against the *current* areas (they may
    // have been edited on the Focus tab after organizing) and attach only a
    // complete partition — a partial one would 400, or overwrite a good grouping.
    const validAreas = new Set(cleanAreas);
    const claimed = new Set<string>();
    const cleanedClusters = clusters
      .map((cluster) => ({
        ...cluster,
        areas: cluster.areas.filter((area) => {
          if (!validAreas.has(area) || claimed.has(area)) return false;
          claimed.add(area);
          return true;
        }),
      }))
      .filter((cluster) => cluster.areas.length > 0);
    if (
      cleanedClusters.length > 0 &&
      cleanAreas.every((area) => claimed.has(area))
    ) {
      nextInterests.clusters = cleanedClusters;
    }
    if (statement.trim()) {
      nextInterests.statement = statement.trim();
    }
    if (keywords.length) {
      nextInterests.keywords = dedupe(keywords);
    }
    if (skills.length) {
      nextInterests.skills = dedupe(skills);
    }
    // Sources are provenance from the import step — preserved, never edited here.
    if (interests?.sources && Object.keys(interests.sources).length) {
      nextInterests.sources = interests.sources;
    }
    const nextEligibility: ProfileEligibility = {
      citizenship: eligCitizenship,
      stage: eligStage,
      fields: eligFields,
      eligible_restrictions: eligRestrictions,
      lab_visible: eligLabVisible,
    };
    // Preserve a career_stage written by another code path; this tab never sets it.
    if (eligibility?.career_stage !== undefined) {
      nextEligibility.career_stage = eligibility.career_stage;
    }
    nextInterests.eligibility = nextEligibility;

    const categories = WATCH_CATEGORIES.filter(
      (category) => watchCats[category.key],
    ).map((category) => category.key);

    try {
      await saveProfileBasics({
        academic_title: role,
        ...(institution.trim() ? { institution: institution.trim() } : {}),
      });
      await confirmInterests(nextInterests);
      await saveWatch({
        // Backstop against a plan downgrade leaving more topics stored than the
        // current cap allows — trims rather than failing the whole save.
        topics: dedupe(watchTopics).slice(0, topicCap),
        categories,
        cadence,
        timezone: zone,
        send_hour_local: sendHour,
        // Only meaningful on weekly cadence, and stored that way: a reader who
        // switches to daily and back should not silently re-enable an opt-in
        // they turned on months ago, but neither should switching to daily
        // erase it. Held as the reader set it, read only where it applies.
        urgent_alerts: urgentAlerts,
        deadline_buffer_days: bufferDays,
        min_paper_window_days: windowDays,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portal", "profile"] }),
        queryClient.invalidateQueries({ queryKey: ["portal", "watch"] }),
      ]);
      onClose();
    } catch (caught) {
      setSaving(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not save your changes. Try again.",
      );
    }
  }

  const panelAbout = (
    <EditorSection
      title="About you"
      description="This calibrates how Mylo weights papers and opportunities for you."
    >
      <div>
        <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
          Your role
        </p>
        <div className="flex flex-wrap gap-2">
          {ROLES.map((option) => (
            <Chip
              key={option.value}
              selected={role === option.value}
              onClick={() => setRole(option.value)}
            >
              {option.label}
            </Chip>
          ))}
        </div>
      </div>
      <EditorField label="Institution">
        <input
          value={institution}
          onChange={(event) => setInstitution(event.target.value)}
          placeholder="University of Example"
          className={inputClass}
        />
      </EditorField>
    </EditorSection>
  );

  const panelFocus = (
    <EditorSection
      title="Research focus"
      description="What Mylo matches against — a statement, the areas you work in, and your semantic fingerprint."
    >
      <EditorField label="Research statement">
        <textarea
          value={statement}
          onChange={(event) => setStatement(event.target.value)}
          rows={5}
          placeholder="A sentence or two about what you research and how."
          className={cn(inputClass, "min-h-28 resize-y py-2.5 leading-relaxed")}
        />
      </EditorField>
      <TokenField
        label="Research areas"
        items={areas}
        onChange={setAreas}
        placeholder="Add an area and press Enter"
      />
      {areas.length < 1 ? (
        <p className="text-xs text-clay">
          Add at least one research area — Mylo can&apos;t match without one.
        </p>
      ) : (
        <p className="text-xs text-[var(--text-muted)]">
          Used to judge how strongly a paper matches you — and to explain why.
        </p>
      )}
      <TokenField
        label="Keywords"
        items={keywords}
        onChange={setKeywords}
        placeholder="Add a keyword and press Enter"
      />
      <TokenField
        label="Skills"
        items={skills}
        onChange={setSkills}
        placeholder="Add a skill and press Enter"
      />
      <p className="text-xs text-[var(--text-muted)]">
        Skills are saved for fellowship matching. They are not used for search yet.
      </p>
    </EditorSection>
  );

  const panelInterests = (
    <EditorSection
      title="Interest clusters"
      description="Group related areas into themes so Mylo can report on each thread of your work separately."
    >
      <ClusterOrganizer
        areas={areas}
        clusters={clusters}
        keywords={keywords}
        statement={statement}
        onChange={setClusters}
        onAreasChange={setAreas}
        onWatchSeed={(topics) => setWatchTopics(topics.slice(0, topicCap))}
        maxClusters={clusterCap}
        maxTopicsPerCluster={clusterTopicCap}
      />
    </EditorSection>
  );

  const panelWatch = (
    <>
      <EditorSection
        title="What Mylo watches"
        description="These topics are exactly what Mylo searches for when scanning for new papers — they are the only thing driving your literature search."
      >
        <TokenField
          label="Watch topics"
          items={watchTopics}
          onChange={setWatchTopics}
          placeholder="Add a topic and press Enter"
          maxItems={topicCap}
        />
      </EditorSection>

      <EditorSection title="Signals to surface">
        <div className="flex flex-col">
          {WATCH_CATEGORIES.map((category) => (
            <EditorToggleRow
              key={category.key}
              label={category.label}
              description={category.desc}
              checked={Boolean(watchCats[category.key])}
              onChange={() =>
                setWatchCats((prev) => ({
                  ...prev,
                  [category.key]: !prev[category.key],
                }))
              }
            />
          ))}
        </div>
      </EditorSection>

    </>
  );

  const panelDelivery = (
    <>
      <EditorSection
        title="How often should Mylo message you?"
        description="Cadence governs Discord only. Mylo scores your feeds and writes your report every day either way, and the web app shows both every day — choosing Weekly asks not to be interrupted, not for Mylo to do less."
      >
        <div className="flex flex-wrap gap-2">
          {CADENCES.map((option) => (
            <Chip
              key={option.id}
              selected={cadence === option.id}
              onClick={() => setCadence(option.id)}
            >
              {option.label}
            </Chip>
          ))}
        </div>
        <p className="text-[12.5px] leading-5 text-[var(--text-secondary)]">
          {cadence === "daily"
            ? "A daily report Tuesday to Friday, and the weekly on Monday. No weekend messages."
            : "One weekly report on Monday morning. No weekend messages."}
        </p>
      </EditorSection>

      <EditorSection
        title="When your morning is"
        description="Mylo compiles overnight and holds the message until this hour in your own time zone."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <EditorField label="Send at">
            <select
              className={inputClass}
              value={sendHour}
              onChange={(event) => setSendHour(Number(event.target.value))}
            >
              {SEND_HOURS.map((hour) => (
                <option key={hour} value={hour}>
                  {hourLabel(hour)}
                </option>
              ))}
            </select>
          </EditorField>
          <EditorField label="Time zone">
            <select
              className={inputClass}
              value={zone}
              onChange={(event) => setZone(event.target.value)}
            >
              {(TIMEZONES.includes(zone) ? TIMEZONES : [zone, ...TIMEZONES]).map(
                (name) => (
                  <option key={name} value={name}>
                    {name.replace(/_/g, " ")}
                  </option>
                ),
              )}
            </select>
          </EditorField>
        </div>
      </EditorSection>

      {cadence === "weekly" ? (
        <EditorSection title="Between Mondays">
          <EditorToggleRow
            label="Urgent deadline alerts"
            description="One message between weeklies, and only when a deadline moves on something you saved that is due inside your buffer."
            checked={urgentAlerts}
            onChange={() => setUrgentAlerts((previous) => !previous)}
          />
        </EditorSection>
      ) : null}

      <EditorSection
        title="Your timeline"
        description="What Mylo treats as enough runway when it judges whether a venue or a call actually fits your plan. Projects can override both."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <EditorField
            label="Deadline buffer (days)"
            hint="Slack you want between finishing something and its deadline. 0–90."
          >
            <input
              className={inputClass}
              type="number"
              min={0}
              max={90}
              value={bufferDays}
              onChange={(event) => setBufferDays(Number(event.target.value))}
            />
          </EditorField>
          <EditorField
            label="Minimum paper window (days)"
            hint="Fewest days you consider enough to write a full paper. 7–365."
          >
            <input
              className={inputClass}
              type="number"
              min={7}
              max={365}
              value={windowDays}
              onChange={(event) => setWindowDays(Number(event.target.value))}
            />
          </EditorField>
        </div>
      </EditorSection>
    </>
  );

  const panelEligibility = (
    <EditorSection
      title="Fellowship eligibility"
      description="Fellowships are matched by eligibility, not just topic. These answers let Mylo filter to what you can actually apply for."
    >
      <div>
        <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
          Citizenship status
        </p>
        <div className="flex flex-wrap gap-2">
          {CITIZENSHIP_OPTIONS.map((option) => (
            <Chip
              key={option.value}
              selected={eligCitizenship === option.value}
              onClick={() => setEligCitizenship(option.value)}
            >
              {option.label}
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
          Career stage
        </p>
        <div className="flex flex-wrap gap-2">
          {STAGE_OPTIONS.map((option) => (
            <Chip
              key={option.value === "" ? "__none__" : option.value}
              selected={eligStage === option.value}
              onClick={() => setEligStage(option.value)}
            >
              {option.label}
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
          Broad fields{" "}
          <span className="text-[var(--text-muted)]">(select any that apply)</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {FIELD_OPTIONS.map((field) => (
            <Chip
              key={field}
              selected={eligFields.includes(field)}
              onClick={() =>
                setEligFields((prev) =>
                  prev.includes(field)
                    ? prev.filter((value) => value !== field)
                    : [...prev, field],
                )
              }
            >
              {field}
            </Chip>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
          Eligible restriction groups{" "}
          <span className="text-[var(--text-muted)]">(optional)</span>
        </p>
        <div className="flex flex-col gap-2">
          {RESTRICTION_OPTIONS.map((group) => (
            <label key={group} className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={eligRestrictions.includes(group)}
                onChange={() =>
                  setEligRestrictions((prev) =>
                    prev.includes(group)
                      ? prev.filter((value) => value !== group)
                      : [...prev, group],
                  )
                }
                className="h-4 w-4 rounded border border-border bg-card accent-primary focus-visible:ring-2 focus-visible:ring-ring"
              />
              <span className="text-[13.5px] font-medium text-[var(--text-primary)]">
                {group}
              </span>
            </label>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-[var(--text-muted)]">
          Some fellowships are restricted to specific groups. Selecting one only
          surfaces more opportunities — it never hides any.
        </p>
      </div>

      <div>
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={eligLabVisible}
            onChange={() => setEligLabVisible((value) => !value)}
            className="mt-0.5 h-4 w-4 rounded border border-border bg-card accent-primary focus-visible:ring-2 focus-visible:ring-ring"
          />
          <span className="text-[13.5px] font-medium text-[var(--text-primary)]">
            Let my labs see which fellowships I&rsquo;m eligible for
          </span>
        </label>
        <p className="mt-1.5 text-xs text-[var(--text-muted)]">
          Off by default. Your labs are never shown fellowships you&rsquo;re{" "}
          <em>not</em> eligible for, so this can&rsquo;t reveal your citizenship or
          career stage.
        </p>
      </div>
    </EditorSection>
  );

  const tabs: EditorTab[] = [
    { id: "about", label: "About you", hint: "Role & institution", content: panelAbout },
    { id: "focus", label: "Research focus", hint: "Statement, areas, keywords", content: panelFocus },
    { id: "interests", label: "Interest clusters", hint: "Group areas into themes", content: panelInterests },
    { id: "watch", label: "What Mylo watches", hint: "Topics and signals", content: panelWatch },
    { id: "delivery", label: "Delivery", hint: "Cadence, send hour, timeline", content: panelDelivery },
  ];
  // Eligibility only matters to someone who wants fellowship recommendations —
  // same rule the onboarding flow applies to its eligibility step.
  if (watchCats.fellowships) {
    tabs.push({
      id: "eligibility",
      label: "Fellowship eligibility",
      hint: "Citizenship, stage, fields",
      content: panelEligibility,
    });
  }

  const activeTab = tabs.some((entry) => entry.id === tab) ? tab : "focus";

  return (
    <EditorModal
      eyebrow="Your profile"
      title="Edit profile"
      subtitle="Everything Mylo uses to find matches for you, in one place."
      tabs={tabs}
      activeTab={activeTab}
      onTabChange={(id) => setTab(id as ProfileEditorTab)}
      onClose={onClose}
      onSave={() => void save()}
      saving={saving}
      error={error}
      saveDisabledReason={
        areas.length < 1
          ? "Add at least one research area on the Research focus tab."
          : null
      }
    />
  );
}
