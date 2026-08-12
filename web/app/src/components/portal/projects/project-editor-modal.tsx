"use client";

import * as React from "react";

import { ClusterOrganizer } from "@/components/onboarding/cluster-organizer";
import {
  EditorField,
  EditorModal,
  EditorSection,
  EditorToggleRow,
  type EditorTab,
} from "@/components/portal/primitives/editor-modal";
import type { ClusterGroup } from "@/lib/auth-types";
import {
  useArchiveProject,
  useUnarchiveProject,
  useUpdateProject,
} from "@/lib/portal/hooks";
import { ProjectCapReachedError } from "@/lib/portal/mutations";
import type {
  BriefingCategory,
  Project,
  ProjectUpdateInput,
} from "@/lib/portal/types";

/** Which panel the modal opens on. */
export type ProjectEditorTab = "details" | "focus" | "mylo";

const INPUT =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Statuses a project can be set to. Free text is still accepted by the API;
 * offering a short list keeps the pill vocabulary consistent across projects. */
const STATUSES = ["Active", "Planning", "In review", "On hold", "Complete"];

/** The four areas Mylo can track for a project, in report order. */
const WATCH_AREAS: { key: BriefingCategory; label: string; desc: string }[] = [
  { key: "papers", label: "Papers", desc: "New literature matching this project." },
  { key: "grants", label: "Grants", desc: "Funding that fits its focus." },
  { key: "fellowships", label: "Fellowships", desc: "Awards for the people on it." },
  { key: "conferences", label: "Conferences", desc: "Venues and calls for papers." },
];

/**
 * Edit everything that makes a project what it is, in one dialog: its name,
 * description, status and progress (Details); the research focus Mylo searches
 * on (Focus); and which areas it tracks, plus archiving (Mylo).
 *
 * The Edit button used to be inert, and a project's focus could only be set
 * during creation — so a project that drifted could never be re-aimed. This is
 * the same `EditorModal` surface the profile and lab editors use, so editing a
 * project feels like editing anything else in the workspace.
 */
export function ProjectEditorModal({
  project,
  initialTab = "details",
  onClose,
}: {
  project: Project;
  initialTab?: ProjectEditorTab;
  onClose: () => void;
}) {
  const save = useUpdateProject();
  const archive = useArchiveProject();
  const unarchive = useUnarchiveProject();

  const [tab, setTab] = React.useState<ProjectEditorTab>(initialTab);
  const [error, setError] = React.useState<string | null>(null);

  // Details
  const [name, setName] = React.useState(project.name);
  const [description, setDescription] = React.useState(project.description ?? "");
  const [status, setStatus] = React.useState(project.status ?? "");
  const [progress, setProgress] = React.useState<string>(
    project.progress === null ? "" : String(project.progress),
  );

  // Focus — seeded from the project's stored focus, re-composable by Mylo.
  const [areas, setAreas] = React.useState<string[]>(project.focus.areas);
  const [clusters, setClusters] = React.useState<ClusterGroup[]>(
    project.focus.clusters,
  );
  const [watchTopics, setWatchTopics] = React.useState<string[]>(
    project.focus.watch_topics,
  );
  const [statement, setStatement] = React.useState(project.focus.statement);
  const [focusTouched, setFocusTouched] = React.useState(false);

  // Mylo
  const [categories, setCategories] = React.useState<BriefingCategory[]>(
    project.watch_categories,
  );

  const toggleCategory = (key: BriefingCategory) => {
    setCategories((current) =>
      current.includes(key)
        ? current.filter((c) => c !== key)
        : [...current, key],
    );
  };

  const trimmedName = name.trim();
  const parsedProgress = progress.trim() === "" ? null : Number(progress);
  const progressInvalid =
    parsedProgress !== null &&
    (!Number.isFinite(parsedProgress) ||
      parsedProgress < 0 ||
      parsedProgress > 100);

  const saveDisabledReason = !trimmedName
    ? "A project needs a name."
    : progressInvalid
      ? "Progress must be a number between 0 and 100."
      : null;

  const handleSave = () => {
    if (saveDisabledReason || save.isPending) {
      return;
    }
    setError(null);
    const patch: ProjectUpdateInput = {
      name: trimmedName,
      description: description.trim(),
      status: status.trim(),
      progress: parsedProgress === null ? null : Math.round(parsedProgress),
      watch_categories: categories,
    };
    // Only send a focus when the reader actually changed one — an untouched
    // focus should not be rewritten (and re-seeded) just because they opened
    // the dialog to rename the project.
    if (focusTouched) {
      patch.focus = {
        areas,
        keywords: project.focus.keywords,
        statement: statement.trim(),
        clusters,
        watch_topics: watchTopics,
      };
    }
    save.mutate(
      { id: project.id, patch },
      {
        onSuccess: onClose,
        onError: (err) => setError((err as Error).message),
      },
    );
  };

  const toggleArchive = () => {
    setError(null);
    if (project.is_archived) {
      unarchive.mutate(project.id, {
        onSuccess: onClose,
        onError: (err) =>
          setError(
            err instanceof ProjectCapReachedError
              ? `Restoring this project would exceed your plan's limit of ${err.cap} projects — archive another first, or upgrade.`
              : (err as Error).message,
          ),
      });
    } else {
      archive.mutate(project.id, {
        onSuccess: onClose,
        onError: (err) => setError((err as Error).message),
      });
    }
  };

  const tabs: EditorTab[] = [
    {
      id: "details",
      label: "Details",
      hint: "Name, description, status",
      content: (
        <EditorSection
          title="Project details"
          description="What this project is called, what it is about, and where it stands."
        >
          <EditorField label="Name">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT}
              placeholder="e.g. Robotic surgery literature review"
            />
          </EditorField>

          <EditorField
            label="Description"
            hint="Shown under the project's title. Leave blank to remove it."
          >
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className={`${INPUT} resize-y`}
              placeholder="What this project is working towards."
            />
          </EditorField>

          <EditorField label="Status" hint="Pick one, or write your own.">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {STATUSES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setStatus(status === option ? "" : option)}
                  aria-pressed={status === option}
                  className={
                    status === option
                      ? "rounded-full border border-primary bg-primary px-3 py-1 text-[12px] font-semibold text-[#fffdf8]"
                      : "rounded-full border border-border bg-surface px-3 py-1 text-[12px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
                  }
                >
                  {option}
                </button>
              ))}
            </div>
            <input
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={INPUT}
              placeholder="No status set"
              aria-label="Status"
            />
          </EditorField>

          <EditorField
            label="Progress"
            hint="A percentage, 0–100. Leave blank to stop tracking it."
          >
            <input
              value={progress}
              onChange={(e) => setProgress(e.target.value)}
              inputMode="numeric"
              className={INPUT}
              placeholder="Not tracked"
            />
          </EditorField>
        </EditorSection>
      ),
    },
    {
      id: "focus",
      label: "Focus",
      hint: "What Mylo searches on",
      content: (
        <EditorSection
          title="Research focus"
          description="The themes and sub-topics this project's daily recommendations run against. Rename, merge, or add topics directly — or describe the project in your own words and let Mylo rebuild them."
        >
          <EditorField
            label="One-line purpose"
            hint="What this project is after. Mylo uses it as context when it composes the themes below."
          >
            <input
              value={statement}
              onChange={(e) => {
                setStatement(e.target.value);
                setFocusTouched(true);
              }}
              className={INPUT}
              placeholder="e.g. Vision-language-action models for surgical assistance"
            />
          </EditorField>

          <ClusterOrganizer
            areas={areas}
            clusters={clusters}
            keywords={project.focus.keywords}
            statement={statement}
            onChange={(next) => {
              setClusters(next);
              setFocusTouched(true);
            }}
            onAreasChange={(next) => {
              setAreas(next);
              setFocusTouched(true);
            }}
            onWatchSeed={(next) => {
              setWatchTopics(next);
              setFocusTouched(true);
            }}
          />
        </EditorSection>
      ),
    },
    {
      id: "mylo",
      label: "Mylo",
      hint: "Tracked areas, archiving",
      content: (
        <>
          <EditorSection
            title="What Mylo tracks"
            description="Turn an area off and this project stops getting new matches for it. Its tab says so rather than sitting empty."
          >
            <div>
              {WATCH_AREAS.map((area) => (
                <EditorToggleRow
                  key={area.key}
                  label={area.label}
                  description={area.desc}
                  checked={categories.includes(area.key)}
                  onChange={() => toggleCategory(area.key)}
                />
              ))}
            </div>
          </EditorSection>

          <EditorSection
            title={project.is_archived ? "Restore" : "Archive"}
            description={
              project.is_archived
                ? "Restoring puts this project back into the daily run. It has to fit within your plan's project limit."
                : "Archiving keeps everything Mylo has already found but stops new search work, and frees a slot against your plan's limit. Nothing is deleted."
            }
          >
            <button
              type="button"
              onClick={toggleArchive}
              disabled={archive.isPending || unarchive.isPending}
              className="rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt disabled:opacity-50"
            >
              {project.is_archived
                ? unarchive.isPending
                  ? "Restoring…"
                  : "Restore project"
                : archive.isPending
                  ? "Archiving…"
                  : "Archive project"}
            </button>
          </EditorSection>
        </>
      ),
    },
  ];

  return (
    <EditorModal
      eyebrow={project.scope === "lab" ? project.scope_name : "Personal project"}
      title={`Edit ${project.name}`}
      subtitle="Change what this project is, and what Mylo watches for it."
      tabs={tabs}
      activeTab={tab}
      onTabChange={(id) => setTab(id as ProjectEditorTab)}
      onClose={onClose}
      onSave={handleSave}
      saving={save.isPending}
      saveDisabledReason={saveDisabledReason}
      error={error}
    />
  );
}
