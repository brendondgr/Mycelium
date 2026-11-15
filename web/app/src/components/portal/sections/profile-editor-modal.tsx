"use client";

import * as React from "react";

import { useQueryClient } from "@tanstack/react-query";

import {
  ClusterOrganizer,
  clampClustersToCaps,
} from "@/components/onboarding/cluster-organizer";
import { Chip, TokenField, dedupe, inputClass } from "@/components/onboarding/fields";
import { InstitutionFromEmail } from "@/components/ui/institution-from-email";
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
  synthesizeProfile,
} from "@/lib/auth-client";
import { useEntitlements, useProfile, useWatch } from "@/lib/portal/hooks";
import type {
  ClusterGroup,
  ProfileEligibility,
  ResearchInterests,
  ResearchSource,
  WatchCadence,
} from "@/lib/auth-types";
import { cn } from "@/lib/utils";

/**
 * Which part of the profile a caller wants to edit.
 *
 * These are *destinations*, not tabs: the editor has three tabs and each of
 * these names a section inside one of them. A card's "Adjust" button says what
 * the reader meant, and the modal resolves it to a tab plus a scroll position —
 * so the card affordances keep working while the tab structure is free to change
 * underneath them.
 */
export type ProfileEditorTab =
  | "about"
  | "focus"
  | "interests"
  | "watch"
  | "delivery"
  | "eligibility"
  | "draft";

/** The three tabs the editor actually renders. */
type PanelId = "research" | "delivery" | "draft";

/** Where each destination lives: the tab that holds it, and the block within. */
const DESTINATIONS: Record<ProfileEditorTab, { panel: PanelId; anchor: string | null }> = {
  focus: { panel: "research", anchor: "focus" },
  interests: { panel: "research", anchor: "interests" },
  watch: { panel: "research", anchor: "watch" },
  about: { panel: "delivery", anchor: "about" },
  delivery: { panel: "delivery", anchor: "delivery" },
  eligibility: { panel: "delivery", anchor: "eligibility" },
  draft: { panel: "draft", anchor: null },
};

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

// The publication sources the personal intake accepts, kept in step with
// `SYNTHESIZE_SOURCES` on the backend and with the onboarding import step — the
// same endpoint serves both, so a value here it does not know is a 400.
type SourceOption = {
  value: ResearchSource;
  label: string;
  tagline: string;
  idLabel: string;
  placeholder: string;
  help: string;
};

const SOURCES: SourceOption[] = [
  {
    value: "openalex",
    label: "OpenAlex",
    tagline: "Open catalog of works & authors",
    idLabel: "OpenAlex author ID or ORCID",
    placeholder: "A5023888391 or 0000-0002-1825-0097",
    help: "The A… id in your OpenAlex author-page URL, or your ORCID.",
  },
  {
    value: "semantic",
    label: "Semantic Scholar",
    tagline: "AI-powered paper graph",
    idLabel: "Semantic Scholar author ID",
    placeholder: "1741101",
    help: "The number in your Semantic Scholar author-page URL.",
  },
  {
    value: "scholar",
    label: "Google Scholar",
    tagline: "Your public Scholar profile",
    idLabel: "Google Scholar profile ID",
    placeholder: "ZQt7m3kAAAAJ",
    help: "The user= value in your Scholar profile URL.",
  },
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
 * writes is on one surface, and it is saved in one action.
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
  // `null` (unlimited) and still-loading both mean no client-side limit.
  const { data: entitlements } = useEntitlements();
  const clusterCap = entitlements?.cluster_cap ?? undefined;
  const clusterTopicCap = entitlements?.cluster_topic_cap ?? undefined;
  const topicCap = entitlements?.topic_cap ?? undefined;

  const interests = profile?.interests;

  const destination = DESTINATIONS[initialTab] ?? DESTINATIONS.focus;
  const [tab, setTab] = React.useState<PanelId>(destination.panel);
  const [role, setRole] = React.useState(
    ROLES.some((option) => option.value === profile?.academic_title)
      ? (profile?.academic_title as string)
      : "researcher",
  );

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
  // Provenance. Carried forward from the saved profile, and replaced only when a
  // fresh Mylo draft brings its own.
  const [sources, setSources] = React.useState<ResearchInterests["sources"]>(
    interests?.sources,
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

  // Source material for Mylo's draft — never persisted, only used to draft.
  const [source, setSource] = React.useState<ResearchSource | "">("");
  const [identifier, setIdentifier] = React.useState("");
  const [resumeFile, setResumeFile] = React.useState<File | null>(null);
  const [drafting, setDrafting] = React.useState(false);
  const [draftError, setDraftError] = React.useState<string | null>(null);
  const [draftNote, setDraftNote] = React.useState<string | null>(null);

  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const sourceOption = SOURCES.find((option) => option.value === source) ?? null;
  const hasDraftInput = Boolean((source && identifier.trim()) || resumeFile);

  /** Fold a fresh Mylo draft into the form. Nothing is saved until Save. */
  function applyDraft(drafted: ResearchInterests) {
    if (drafted.statement) setStatement(drafted.statement);
    if (drafted.areas?.length) setAreas(dedupe(drafted.areas));
    if (drafted.keywords?.length) setKeywords(dedupe(drafted.keywords));
    if (drafted.skills?.length) setSkills(dedupe(drafted.skills));
    if (drafted.sources) setSources(drafted.sources);
    // Mylo builds theme clusters during synthesis — carry them in (clamped to
    // the plan) so the organizer opens pre-grouped rather than empty.
    if (drafted.clusters?.length) {
      setClusters(
        clampClustersToCaps(drafted.clusters, {
          maxClusters: clusterCap,
          maxTopicsPerCluster: clusterTopicCap,
        }),
      );
    }
    // Only seed the watch topics when the reader has none; these are what Mylo
    // actually searches for, and overwriting a curated list would be a silent
    // change to their literature search.
    setWatchTopics((previous) =>
      previous.length
        ? previous
        : dedupe([...(drafted.areas ?? []), ...(drafted.keywords ?? [])]).slice(
            0,
            topicCap,
          ),
    );
  }

  async function runDraft() {
    setDraftError(null);
    setDraftNote(null);
    setDrafting(true);
    try {
      const result = await synthesizeProfile({
        source: source || undefined,
        identifier: identifier.trim() || undefined,
        resume: resumeFile,
      });
      applyDraft(result.interests);
      setDraftNote(
        "Mylo drafted your profile — review it on the Research profile tab before saving.",
      );
    } catch (caught) {
      setDraftError(
        caught instanceof Error
          ? caught.message
          : "Could not build your profile. Try again.",
      );
    } finally {
      setDrafting(false);
    }
  }

  async function save() {
    setError(null);
    setSaving(true);

    const cleanAreas = dedupe(areas);
    const nextInterests: ResearchInterests = { version: 2, areas: cleanAreas };

    // The interests contract requires that IF `clusters` is present, every area
    // sits in exactly one cluster. Sanitize against the *current* areas (they may
    // have been edited above after organizing) and attach only a complete
    // partition — a partial one would 400, or overwrite a good grouping.
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
    // Sources are provenance from an import — preserved, never edited by hand.
    if (sources && Object.keys(sources).length) {
      nextInterests.sources = sources;
    }
    const nextEligibility: ProfileEligibility = {
      citizenship: eligCitizenship,
      stage: eligStage,
      fields: eligFields,
      eligible_restrictions: eligRestrictions,
      lab_visible: eligLabVisible,
    };
    // Preserve a career_stage written by another code path; this form never sets it.
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

  // -- Research profile --------------------------------------------------
  //
  // One tab for the whole matching chain, in the order it actually runs: what
  // you work on, how those areas are grouped into themes, what Mylo searches for
  // on the back of them, and which kinds of result it surfaces. These were four
  // tabs, and editing an area silently changed what the clusters tab showed —
  // the reader had to leave the page they were on to see the consequence of the
  // edit they had just made.

  const panelResearch = (
    <>
      <EditorSection
        title="Research focus"
        description="What Mylo matches against — a statement, the areas you work in, and your keywords."
        anchorId="focus"
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

      <EditorSection
        title="Interest clusters"
        description="Group the areas above into themes so Mylo can report on each thread of your work separately."
        anchorId="interests"
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

      <EditorSection
        title="What Mylo watches"
        description="These topics are exactly what Mylo searches for when scanning for new papers — they are the only thing driving your literature search."
        anchorId="watch"
      >
        <TokenField
          label="Watch topics"
          items={watchTopics}
          onChange={setWatchTopics}
          placeholder="Add a topic and press Enter"
          maxItems={topicCap}
        />
      </EditorSection>

      <EditorSection
        title="Signals to surface"
        description="Which kinds of result Mylo brings you. Turning Fellowships off leaves your eligibility answers saved, on the You &amp; delivery tab — it just stops Mylo looking."
        anchorId="signals"
      >
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

  // -- You & delivery ------------------------------------------------------
  //
  // Who you are, when the message lands, and what you can apply for. The
  // eligibility block used to be a tab that appeared and disappeared as the
  // Fellowships signal was toggled on another tab; it is always here now, and
  // says for itself when it is not being used.

  const panelDelivery = (
    <>
      <EditorSection
        title="About you"
        description="This calibrates how Mylo weights papers and opportunities for you."
        anchorId="about"
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
        {/* Not an `EditorField`: that wraps its child in a `<label>`, and this is
            not a control — the institution comes from the verified email. */}
        <div className="block">
          <p
            className="mb-1.5 block text-[13px] font-medium text-[var(--text-primary)]"
            id="profile-institution-label"
          >
            Institution
          </p>
          <InstitutionFromEmail labelledBy="profile-institution-label" />
        </div>
      </EditorSection>

      <EditorSection
        title="How often should Mylo message you?"
        description="Cadence governs Discord only. Mylo scores your feeds and writes your report every day either way, and the web app shows both every day — choosing Weekly asks not to be interrupted, not for Mylo to do less."
        anchorId="delivery"
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
            ? "A daily report every morning, weekends included."
            : "One weekly report on Monday morning, and nothing in between."}
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

      <EditorSection
        title="Fellowship eligibility"
        description="Fellowships are matched by eligibility, not just topic. These answers let Mylo filter to what you can actually apply for."
        anchorId="eligibility"
      >
        {!watchCats.fellowships ? (
          <p className="rounded-xl bg-surface-alt px-3.5 py-2.5 text-[12.5px] leading-5 text-[var(--text-secondary)]">
            Fellowships are switched off under <strong>Signals to surface</strong>{" "}
            on the Research profile tab, so Mylo isn&rsquo;t looking for any right
            now. These answers are still saved and take effect the moment you turn
            that signal back on.
          </p>
        ) : null}

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
    </>
  );

  // -- Draft with Mylo -----------------------------------------------------
  //
  // The lab editor has had this since it shipped; a person could only get it by
  // re-entering onboarding, which is exactly what this dialog exists to avoid.
  // Same endpoint the import step calls, and the same rule: nothing is written
  // until Save, so a draft the reader dislikes costs them a Cancel.

  const panelDraft = (
    <EditorSection
      title="Draft with Mylo"
      description="Point Mylo at your published work, or hand it your CV, and it will write your statement, areas, keywords, and skills for you. Optional — every field stays editable by hand."
    >
      <div className="space-y-3">
        <p className="text-[13px] font-medium text-[var(--text-primary)]">
          Choose one source{" "}
          <span className="text-[var(--text-muted)]">(optional)</span>
        </p>
        <div
          role="radiogroup"
          aria-label="Publication source"
          className="grid gap-3 sm:grid-cols-3"
        >
          {SOURCES.map((option) => {
            const selected = source === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setSource(selected ? "" : option.value)}
                className={cn(
                  "rounded-lg border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  selected
                    ? "border-primary bg-secondary"
                    : "border-border bg-card hover:border-brand-secondary",
                )}
              >
                <span className="block text-[13px] font-semibold text-[var(--text-primary)]">
                  {option.label}
                </span>
                <span className="mt-1 block text-[11.5px] text-[var(--text-muted)]">
                  {option.tagline}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {sourceOption ? (
        <EditorField label={sourceOption.idLabel} hint={sourceOption.help}>
          <input
            type="text"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            placeholder={sourceOption.placeholder}
            className={inputClass}
          />
        </EditorField>
      ) : null}

      <div className="space-y-2">
        <p className="text-[13px] font-medium text-[var(--text-primary)]">
          Upload a résumé or CV{" "}
          <span className="text-[var(--text-muted)]">(optional)</span>
        </p>
        <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-card px-4 py-3 text-[13px] transition hover:border-brand-secondary focus-within:ring-2 focus-within:ring-ring">
          <span
            className={
              resumeFile ? "text-foreground" : "text-[var(--text-muted)]"
            }
          >
            {resumeFile?.name ?? "Choose a PDF or text file"}
          </span>
          <span className="rounded-full border border-border px-3 py-1 text-[11.5px] font-medium text-[var(--text-secondary)]">
            Browse
          </span>
          <input
            type="file"
            accept=".pdf,.txt,.text,.md,.markdown,text/plain,application/pdf"
            className="sr-only"
            onChange={(event) => {
              setResumeFile(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
        </label>
        {resumeFile ? (
          <button
            type="button"
            onClick={() => setResumeFile(null)}
            className="text-[11.5px] font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
          >
            Remove file
          </button>
        ) : null}
        <p className="text-[11.5px] text-[var(--text-muted)]">
          Mylo reads it to draft your interests, then discards the file.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          onClick={() => void runDraft()}
          disabled={drafting || !hasDraftInput}
        >
          {/* Small decorative brand mark — a plain img is right here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/mylo-portrait-64.webp"
            alt=""
            width={20}
            height={20}
            className="h-5 w-5 rounded-full object-cover"
          />
          {drafting ? "Mylo is drafting…" : "Draft with Mylo"}
        </button>
        {draftNote ? (
          <span className="text-[12.5px] text-primary">{draftNote}</span>
        ) : null}
      </div>
      {!hasDraftInput ? (
        <p className="text-[11.5px] text-[var(--text-muted)]">
          Pick a source and enter your id, upload a CV, or both.
        </p>
      ) : null}
      {draftError ? (
        <p className="text-[12.5px] text-clay" role="alert">
          {draftError}
        </p>
      ) : null}
      <p className="text-[12.5px] leading-5 text-[var(--text-secondary)]">
        A draft replaces the statement, areas, keywords, and skills on the
        Research profile tab. Nothing is written to your account until you press
        Save — Cancel discards the whole draft.
      </p>
    </EditorSection>
  );

  const tabs: EditorTab[] = [
    {
      id: "research",
      label: "Research profile",
      hint: "Focus, themes, and what Mylo watches",
      content: panelResearch,
    },
    {
      id: "delivery",
      label: "You & delivery",
      hint: "Role, cadence, timeline, eligibility",
      content: panelDelivery,
    },
    {
      id: "draft",
      label: "Draft with Mylo",
      hint: "Rewrite from your work or CV",
      content: panelDraft,
    },
  ];

  return (
    <EditorModal
      eyebrow="Your profile"
      title="Edit profile"
      subtitle="Everything Mylo uses to find matches for you, in one place."
      tabs={tabs}
      activeTab={tab}
      initialAnchor={destination.anchor}
      onTabChange={(id) => setTab(id as PanelId)}
      onClose={onClose}
      onSave={() => void save()}
      saving={saving}
      error={error}
      saveDisabledReason={
        areas.length < 1
          ? "Add at least one research area under Research focus."
          : null
      }
    />
  );
}
