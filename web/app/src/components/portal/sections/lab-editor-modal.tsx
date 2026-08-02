"use client";

import * as React from "react";

import { ClusterOrganizer } from "@/components/onboarding/cluster-organizer";
import { Chip, TokenField, dedupe, inputClass } from "@/components/onboarding/fields";
import { CloseIcon, DocumentIcon } from "@/components/portal/icons";
import {
  EditorField,
  EditorModal,
  EditorSection,
  EditorToggleRow,
  type EditorTab,
} from "@/components/portal/primitives/editor-modal";
import {
  useLabProfile,
  useLabWatch,
  useSynthesizeLabProfile,
  useUpdateLabProfile,
  useUpdateLabWatch,
} from "@/lib/portal/hooks";
import type { ClusterGroup, WatchCadence } from "@/lib/auth-types";
import type { LabProfileData, MyLab, WatchData } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Which panel the modal opens on. */
export type LabEditorTab = "draft" | "purpose" | "focus" | "watch";

// Signal kinds a lab can ask Mylo to surface. Conferences sit alongside grants as
// a lab-level, purpose-driven signal.
const WATCH_CATEGORIES = [
  { key: "papers", label: "New papers & preprints", desc: "Relevant to the lab's areas." },
  { key: "grants", label: "Grant opportunities", desc: "Funding that fits the lab." },
  { key: "conferences", label: "Conferences & CFPs", desc: "Venues matching the lab's purpose." },
  { key: "fellowships", label: "Fellowships", desc: "For the lab's students and trainees." },
  { key: "collaborators", label: "Potential collaborators", desc: "Groups on adjacent problems." },
];

const CADENCES: { id: WatchCadence; label: string }[] = [
  { id: "daily", label: "Daily digest" },
  { id: "weekly", label: "Weekly digest" },
];

const DEFAULT_CATS = ["papers", "grants", "conferences"];
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const WATCH_SEED_LIMIT = 12;

/** Split a comma-separated field into a trimmed, non-empty list. */
function parseList(text: string): string[] {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** Pull the (untyped) `clusters` array off a lab's stored `interests` blob. */
function readClusters(
  interests: Record<string, unknown> | undefined | null,
): ClusterGroup[] {
  const raw = interests?.clusters;
  return Array.isArray(raw) ? (raw as ClusterGroup[]) : [];
}

function readKeywords(
  interests: Record<string, unknown> | undefined | null,
): string[] {
  const raw = interests?.keywords;
  return Array.isArray(raw) ? (raw as string[]) : [];
}

/**
 * Edit a lab's whole profile in one dialog — the lab twin of
 * `ProfileEditorModal`, and the only place a lab's purpose, focus areas, and
 * watch settings are written.
 *
 * "Purpose & goals" used to be an inline form inside a page card, and the watch
 * settings had a read-only card with no editing surface at all: a lab's cadence
 * could only be changed by re-running the whole setup flow. Both now live here,
 * one tab apart.
 */
export function LabEditorModal({
  lab,
  initialTab = "purpose",
  onClose,
}: {
  lab: MyLab;
  initialTab?: LabEditorTab;
  onClose: () => void;
}) {
  const profileQuery = useLabProfile(lab.slug);
  const watchQuery = useLabWatch(lab.slug);

  // Both reads are normally already warm from the page behind the dialog.
  if (profileQuery.isLoading || watchQuery.isLoading) {
    return (
      <EditorModal
        eyebrow="Lab profile"
        title={`Edit ${lab.name}`}
        tabs={[
          {
            id: "loading",
            label: "Loading",
            content: <div className="h-40 animate-pulse rounded-xl bg-surface-alt" />,
          },
        ]}
        activeTab="loading"
        onTabChange={() => {}}
        onClose={onClose}
        onSave={() => {}}
        saveDisabledReason="Loading the lab profile…"
      />
    );
  }

  return (
    <LabEditorForm
      lab={lab}
      initialTab={initialTab}
      profile={profileQuery.data}
      watch={watchQuery.data}
      onClose={onClose}
    />
  );
}

function LabEditorForm({
  lab,
  initialTab,
  profile,
  watch,
  onClose,
}: {
  lab: MyLab;
  initialTab: LabEditorTab;
  profile: LabProfileData | undefined;
  watch: WatchData | undefined;
  onClose: () => void;
}) {
  const synthesize = useSynthesizeLabProfile(lab.slug);
  const saveProfile = useUpdateLabProfile(lab.slug);
  const saveWatch = useUpdateLabWatch(lab.slug);

  const [tab, setTab] = React.useState<LabEditorTab>(initialTab);

  // Source material for Mylo's draft — never persisted, only used to draft.
  const [description, setDescription] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [links, setLinks] = React.useState("");
  const [synthError, setSynthError] = React.useState<string | null>(null);
  const [synthNote, setSynthNote] = React.useState<string | null>(null);

  const [statement, setStatement] = React.useState(profile?.statement ?? "");
  const [areas, setAreas] = React.useState<string[]>(profile?.areas ?? []);
  const [keywords, setKeywords] = React.useState<string[]>(
    readKeywords(profile?.interests),
  );
  const [clusters, setClusters] = React.useState<ClusterGroup[]>(
    readClusters(profile?.interests),
  );
  const [funding, setFunding] = React.useState(
    (profile?.funding_needs ?? []).join(", "),
  );
  const [strategic, setStrategic] = React.useState(
    (profile?.strategic_needs ?? []).join(", "),
  );

  const [watchTopics, setWatchTopics] = React.useState<string[]>(
    watch?.topics ?? [],
  );
  const [watchCats, setWatchCats] = React.useState<string[]>(
    watch?.categories?.length ? watch.categories : DEFAULT_CATS,
  );
  const [cadence, setCadence] = React.useState<WatchCadence>(
    watch?.cadence ?? "weekly",
  );

  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function runSynthesis() {
    setSynthError(null);
    setSynthNote(null);
    const linkList = links
      .split(/[\n,]/)
      .map((link) => link.trim())
      .filter(Boolean);
    synthesize.mutate(
      { description, areas, links: linkList, files },
      {
        onSuccess: (result) => {
          if (result.statement) setStatement(result.statement);
          if (result.areas?.length) setAreas(dedupe(result.areas));
          if (result.keywords?.length) setKeywords(dedupe(result.keywords));
          if (watchTopics.length === 0) {
            setWatchTopics(
              dedupe([...(result.areas ?? []), ...(result.keywords ?? [])]).slice(
                0,
                WATCH_SEED_LIMIT,
              ),
            );
          }
          setSynthNote(
            "Mylo drafted the profile — review it on the Purpose and Focus areas tabs before saving.",
          );
        },
        onError: (caught) => setSynthError((caught as Error).message),
      },
    );
  }

  async function save() {
    setError(null);
    setSaving(true);

    const cleanAreas = dedupe(areas);
    const cleanKeywords = dedupe(keywords);
    const seedTopics = watchTopics.length
      ? watchTopics
      : dedupe([...cleanAreas, ...cleanKeywords]).slice(0, WATCH_SEED_LIMIT);

    const payload: Parameters<typeof saveProfile.mutateAsync>[0] = {
      statement: statement.trim(),
      areas: cleanAreas,
      funding_needs: parseList(funding),
      strategic_needs: parseList(strategic),
    };

    // The interests contract requires at least one area, and — if `clusters` is
    // present — a complete partition of those areas. Sanitize against the current
    // areas and attach the grouping only when it covers every one of them, so a
    // stale grouping never overwrites a good saved one or 400s the save.
    if (cleanAreas.length > 0) {
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
      const interests: Record<string, unknown> = {
        ...(profile?.interests ?? {}),
        version: 2,
        areas: cleanAreas,
        keywords: cleanKeywords,
        statement: statement.trim(),
      };
      if (
        cleanedClusters.length > 0 &&
        cleanAreas.every((area) => claimed.has(area))
      ) {
        interests.clusters = cleanedClusters;
      } else {
        delete interests.clusters;
      }
      payload.interests = interests;
    }

    try {
      await saveProfile.mutateAsync(payload);
      await saveWatch.mutateAsync({
        topics: dedupe(seedTopics),
        categories: watchCats,
        cadence,
      });
      onClose();
    } catch (caught) {
      setSaving(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not save the lab profile. Try again.",
      );
    }
  }

  const panelDraft = (
    <EditorSection
      title="Draft with Mylo"
      description="Describe the lab, drop source files, or paste profile links and Mylo will write the purpose, focus areas, and keywords for you. Optional — every field is editable by hand."
    >
      <EditorField label="Lab description">
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={5}
          placeholder="e.g. We study coral-reef resilience under ocean warming, combining remote sensing with machine learning."
          className={cn(inputClass, "min-h-28 resize-y py-2.5")}
        />
      </EditorField>

      <div className="grid gap-4 md:grid-cols-2">
        <EditorField label="Source files">
          <DropZone files={files} onChange={setFiles} />
        </EditorField>
        <EditorField
          label="Source links"
          hint="Google Scholar, Semantic Scholar, OpenAlex, or ORCID profiles."
        >
          <textarea
            value={links}
            onChange={(event) => setLinks(event.target.value)}
            rows={5}
            placeholder={
              "Paste profile links (one per line):\n" +
              "https://scholar.google.com/citations?user=…\n" +
              "https://www.semanticscholar.org/author/…"
            }
            className={cn(inputClass, "min-h-32 resize-y py-2.5")}
          />
        </EditorField>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          onClick={runSynthesis}
          disabled={
            synthesize.isPending ||
            (!description.trim() && !links.trim() && files.length === 0)
          }
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
          {synthesize.isPending ? "Mylo is drafting…" : "Draft with Mylo"}
        </button>
        {synthNote ? (
          <span className="text-[12.5px] text-primary">{synthNote}</span>
        ) : null}
      </div>
      {synthError ? (
        <p className="text-[12.5px] text-clay" role="alert">
          {synthError}
        </p>
      ) : null}
    </EditorSection>
  );

  const panelPurpose = (
    <EditorSection
      title="Purpose & goals"
      description="The lab's collective direction — what Mylo grounds every lab recommendation in."
    >
      <EditorField label="Statement of purpose">
        <textarea
          value={statement}
          onChange={(event) => setStatement(event.target.value)}
          rows={6}
          placeholder="The lab's shared research purpose."
          className={cn(inputClass, "min-h-32 resize-y py-2.5 leading-relaxed")}
        />
      </EditorField>
      <EditorField
        label="Funding needs"
        hint="Comma-separated — used to weight grant matches."
      >
        <input
          value={funding}
          onChange={(event) => setFunding(event.target.value)}
          placeholder="NSF, NIH R01"
          className={inputClass}
        />
      </EditorField>
      <EditorField
        label="Strategic needs"
        hint="Comma-separated — what the lab is trying to build or hire toward."
      >
        <input
          value={strategic}
          onChange={(event) => setStrategic(event.target.value)}
          placeholder="New postdoc, GPU cluster"
          className={inputClass}
        />
      </EditorField>
    </EditorSection>
  );

  const panelFocus = (
    <>
      <EditorSection
        title="Focus areas"
        description="The research areas and keywords Mylo matches papers, grants, and conferences against."
      >
        <TokenField
          label="Research focus areas"
          items={areas}
          onChange={setAreas}
          placeholder="Add an area and press Enter"
        />
        {areas.length < 1 ? (
          <p className="text-xs text-clay">
            Add at least one focus area — Mylo can&apos;t match the lab without one.
          </p>
        ) : null}
        <TokenField
          label="Tags & keywords"
          items={keywords}
          onChange={setKeywords}
          placeholder="Add a keyword and press Enter"
        />
      </EditorSection>

      <EditorSection
        title="Interest clusters"
        description="Group related areas into themes so Mylo can report on each thread of the lab's work separately."
      >
        <ClusterOrganizer
          areas={areas}
          clusters={clusters}
          keywords={keywords}
          statement={statement}
          onChange={setClusters}
          onAreasChange={setAreas}
          onWatchSeed={(topics) => setWatchTopics(topics.slice(0, WATCH_SEED_LIMIT))}
        />
      </EditorSection>
    </>
  );

  const panelWatch = (
    <>
      <EditorSection
        title="What Mylo watches"
        description="The topics Mylo searches for on the lab's behalf. Left empty, they are seeded from the focus areas and keywords on save."
      >
        <TokenField
          label="Topics Mylo monitors for the lab"
          items={watchTopics}
          onChange={setWatchTopics}
          placeholder="Add a topic and press Enter"
        />
      </EditorSection>

      <EditorSection title="Signals to surface">
        <div className="flex flex-col">
          {WATCH_CATEGORIES.map((category) => (
            <EditorToggleRow
              key={category.key}
              label={category.label}
              description={category.desc}
              checked={watchCats.includes(category.key)}
              onChange={() =>
                setWatchCats((prev) =>
                  prev.includes(category.key)
                    ? prev.filter((value) => value !== category.key)
                    : [...prev, category.key],
                )
              }
            />
          ))}
        </div>
      </EditorSection>

      <EditorSection title="How often should Mylo report?">
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
      </EditorSection>
    </>
  );

  const tabs: EditorTab[] = [
    { id: "purpose", label: "Purpose & goals", hint: "Statement, funding, needs", content: panelPurpose },
    { id: "focus", label: "Focus areas", hint: "Areas, keywords, clusters", content: panelFocus },
    { id: "watch", label: "What Mylo watches", hint: "Topics, signals, cadence", content: panelWatch },
    { id: "draft", label: "Draft with Mylo", hint: "Rewrite from source material", content: panelDraft },
  ];

  return (
    <EditorModal
      eyebrow="Lab profile"
      title={`Edit ${lab.name}`}
      subtitle="The lab's purpose, focus, and what Mylo watches — all in one place."
      tabs={tabs}
      activeTab={tab}
      onTabChange={(id) => setTab(id as LabEditorTab)}
      onClose={onClose}
      onSave={() => void save()}
      saving={saving}
      error={error}
      saveDisabledReason={
        statement.trim().length === 0 && areas.length === 0
          ? "Add a statement or at least one focus area before saving."
          : null
      }
    />
  );
}

// -- Drag-and-drop file input ------------------------------------------------

function DropZone({
  files,
  onChange,
}: {
  files: File[];
  onChange: (next: File[]) => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list).filter((file) => file.size <= MAX_FILE_BYTES);
    const merged = [...files];
    for (const file of incoming) {
      if (!merged.some((m) => m.name === file.name && m.size === file.size)) {
        merged.push(file);
      }
    }
    onChange(merged);
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex min-h-32 w-full flex-col items-center justify-center gap-1.5 rounded-md border border-dashed px-3 py-4 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          dragging
            ? "border-primary bg-primary/5"
            : "border-input bg-card hover:bg-surface-alt",
        )}
      >
        <DocumentIcon size={20} className="text-brand-secondary" />
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          Drop files here
        </span>
        <span className="text-[11.5px] text-[var(--text-secondary)]">
          or click to browse · PDF or text
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.doc,.docx,application/pdf,text/plain"
        className="hidden"
        onChange={(event) => {
          addFiles(event.target.files);
          event.target.value = "";
        }}
      />
      {files.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {files.map((file) => (
            <li
              key={`${file.name}:${file.size}`}
              className="flex items-center justify-between gap-2 rounded-md bg-surface-alt px-2.5 py-1.5 text-[12px]"
            >
              <span className="truncate text-[var(--text-secondary)]">
                {file.name}
              </span>
              <button
                type="button"
                aria-label={`Remove ${file.name}`}
                onClick={() => onChange(files.filter((f) => f !== file))}
                className="shrink-0 text-[var(--text-secondary)] hover:text-foreground"
              >
                <CloseIcon size={13} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
