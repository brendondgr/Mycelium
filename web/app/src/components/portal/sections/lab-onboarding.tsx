"use client";

import * as React from "react";

import { Chip, TokenField, dedupe, inputClass } from "@/components/onboarding/fields";
import { CloseIcon, DocumentIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import {
  useLabProfile,
  useLabWatch,
  useSynthesizeLabProfile,
  useUpdateLabProfile,
  useUpdateLabWatch,
} from "@/lib/portal/hooks";
import type { WatchCadence } from "@/lib/auth-types";
import type { MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

// Signal kinds a lab can ask Milo to surface. Conferences sit alongside grants
// as a lab-level, purpose-driven signal (see the lab overview metrics).
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

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/** Prefilled values for editing an already-configured lab. */
export type LabEditorInitial = {
  statement: string;
  areas: string[];
  keywords: string[];
  watchTopics: string[];
  watchCats: string[];
  cadence: WatchCadence;
};

/**
 * The lab setup/edit surface. A thin wrapper that reuses the already-cached lab
 * profile + watch queries (so opening "Edit setup" is instant — no extra
 * round-trips) and hands the settled values to the single-page form as
 * ``initial`` (lazy state seed — no set-state-in-effect).
 */
export function LabEditor({
  lab,
  mode = "create",
  onDone,
  onCancel,
}: {
  lab: MyLab;
  mode?: "create" | "edit";
  onDone?: () => void;
  onCancel?: () => void;
}) {
  const profileQuery = useLabProfile(lab.slug);
  const watchQuery = useLabWatch(lab.slug);

  // Create mode starts blank; edit mode waits for the (usually cached) values.
  const ready =
    mode === "create" || (!profileQuery.isLoading && !watchQuery.isLoading);

  if (!ready) {
    return (
      <Card accent="primary-rule" className="p-6">
        <div className="h-40 animate-pulse rounded-xl bg-surface-alt" />
      </Card>
    );
  }

  const profile = profileQuery.data;
  const watch = watchQuery.data;
  const initial: LabEditorInitial | undefined =
    mode === "edit"
      ? {
          statement: profile?.statement ?? "",
          areas: profile?.areas ?? [],
          keywords: Array.isArray(profile?.interests?.keywords)
            ? (profile?.interests?.keywords as string[])
            : [],
          watchTopics: watch?.topics ?? [],
          watchCats: watch?.categories?.length ? watch.categories : DEFAULT_CATS,
          cadence: watch?.cadence ?? "weekly",
        }
      : undefined;

  return (
    <LabEditorForm
      key={`${lab.slug}:${mode}`}
      lab={lab}
      mode={mode}
      initial={initial}
      onDone={() => {
        onDone?.();
        profileQuery.refetch();
        watchQuery.refetch();
      }}
      onCancel={onCancel}
    />
  );
}

/**
 * Single-page lab setup: describe the lab + drop source files / paste profile
 * links, let Milo draft the purpose/areas/keywords, review and adjust, set what
 * Milo watches, and save — all on one page.
 */
function LabEditorForm({
  lab,
  mode,
  initial,
  onDone,
  onCancel,
}: {
  lab: MyLab;
  mode: "create" | "edit";
  initial?: LabEditorInitial;
  onDone?: () => void;
  onCancel?: () => void;
}) {
  const synthesize = useSynthesizeLabProfile(lab.slug);
  const saveProfile = useUpdateLabProfile(lab.slug);
  const saveWatch = useUpdateLabWatch(lab.slug);
  const editing = mode === "edit";

  // Source material for Milo's draft.
  const [description, setDescription] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [links, setLinks] = React.useState("");
  const [synthError, setSynthError] = React.useState<string | null>(null);
  const [synthNote, setSynthNote] = React.useState<string | null>(null);

  // The (draftable, editable) profile fields.
  const [statement, setStatement] = React.useState(initial?.statement ?? "");
  const [areas, setAreas] = React.useState<string[]>(initial?.areas ?? []);
  const [keywords, setKeywords] = React.useState<string[]>(
    initial?.keywords ?? [],
  );

  // What Milo watches.
  const [watchTopics, setWatchTopics] = React.useState<string[]>(
    initial?.watchTopics ?? [],
  );
  const [watchCats, setWatchCats] = React.useState<string[]>(
    initial?.watchCats ?? DEFAULT_CATS,
  );
  const [cadence, setCadence] = React.useState<WatchCadence>(
    initial?.cadence ?? "weekly",
  );
  const [saveError, setSaveError] = React.useState<string | null>(null);

  function runSynthesis() {
    setSynthError(null);
    setSynthNote(null);
    const linkList = links
      .split(/[\n,]/)
      .map((l) => l.trim())
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
                12,
              ),
            );
          }
          setSynthNote("Milo drafted the profile below — edit anything before saving.");
        },
        onError: (e) => setSynthError((e as Error).message),
      },
    );
  }

  function toggleCat(key: string) {
    setWatchCats((prev) =>
      prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key],
    );
  }

  function finish() {
    setSaveError(null);
    const cleanAreas = dedupe(areas);
    const cleanKeywords = dedupe(keywords);
    const seedTopics = watchTopics.length
      ? watchTopics
      : dedupe([...cleanAreas, ...cleanKeywords]).slice(0, 12);

    const profilePayload: Parameters<typeof saveProfile.mutate>[0] = {
      statement: statement.trim(),
      areas: cleanAreas,
    };
    // Keywords live inside the interests contract, which requires ≥1 area.
    if (cleanAreas.length > 0) {
      profilePayload.interests = {
        version: 1,
        areas: cleanAreas,
        keywords: cleanKeywords,
        statement: statement.trim(),
      };
    }

    saveProfile.mutate(profilePayload, {
      onSuccess: () => {
        saveWatch.mutate(
          { topics: dedupe(seedTopics), categories: watchCats, cadence },
          {
            onSuccess: () => onDone?.(),
            onError: (e) => setSaveError((e as Error).message),
          },
        );
      },
      onError: (e) => setSaveError((e as Error).message),
    });
  }

  const saving = saveProfile.isPending || saveWatch.isPending;
  const canSave = statement.trim().length > 0 || areas.length > 0;

  return (
    <Card accent="primary-rule" className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="m-0 font-serif text-[26px] font-semibold leading-tight text-[var(--text-primary)]">
          Describe the lab.
        </h1>
        <p className="mt-1.5 max-w-xl text-[14px] text-[var(--text-secondary)]">
          Describe your lab and Milo will create the rest of it for you.
        </p>
      </div>

      {/* Describe + source material — three columns */}
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Lab description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            placeholder="e.g. We study coral-reef resilience under ocean warming, combining remote sensing with machine learning."
            className={cn(inputClass, "min-h-36 resize-y py-2")}
          />
        </Field>

        <Field label="Source files">
          <DropZone files={files} onChange={setFiles} />
        </Field>

        <Field label="Source links">
          <textarea
            value={links}
            onChange={(e) => setLinks(e.target.value)}
            rows={6}
            placeholder={
              "Paste profile links (one per line):\n" +
              "https://scholar.google.com/citations?user=…\n" +
              "https://www.semanticscholar.org/author/…"
            }
            className={cn(inputClass, "min-h-36 resize-y py-2")}
          />
          <p className="mt-1 text-[11.5px] text-[var(--text-muted)]">
            Google Scholar, Semantic Scholar, OpenAlex, or ORCID profiles.
          </p>
        </Field>
      </div>

      {/* Draft with Milo */}
      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={PRIMARY_BUTTON}
          onClick={runSynthesis}
          disabled={
            synthesize.isPending ||
            (!description.trim() && !links.trim() && files.length === 0)
          }
        >
          {/* Small decorative brand mark — a plain img is right here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/mylo-headshot.webp"
            alt=""
            width={20}
            height={20}
            className="h-5 w-5 rounded-full object-cover"
          />
          {synthesize.isPending ? "Milo is drafting…" : "Draft with Milo"}
        </button>
        {synthNote ? (
          <span className="text-[12.5px] text-primary">{synthNote}</span>
        ) : (
          <span className="text-[12px] text-[var(--text-muted)]">
            Optional — you can also fill everything in by hand.
          </span>
        )}
      </div>
      {synthError ? (
        <p className="mt-2 text-[12.5px] text-clay" role="alert">
          {synthError}
        </p>
      ) : null}

      <Divider />

      {/* Milo's draft — editable. Statement (left) · areas + keywords (right). */}
      <SectionTitle>The lab profile</SectionTitle>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Statement of purpose">
          <textarea
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            rows={6}
            placeholder="The lab's shared research purpose."
            className={cn(inputClass, "min-h-36 resize-y py-2")}
          />
        </Field>
        <div className="space-y-4">
          <TokenField
            label="Research focus areas"
            items={areas}
            onChange={setAreas}
            placeholder="Add an area, press Enter"
          />
          <TokenField
            label="Tags & keywords"
            items={keywords}
            onChange={setKeywords}
            placeholder="Add a keyword, press Enter"
          />
        </div>
      </div>

      <Divider />

      {/* What Milo watches. Topics + cadence (left) · signals (two columns right). */}
      <SectionTitle>What Milo watches</SectionTitle>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-4">
          <TokenField
            label="Topics Milo monitors for the lab"
            items={watchTopics}
            onChange={setWatchTopics}
            placeholder="Add a topic, press Enter"
          />
          <div>
            <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
              How often
            </p>
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
          </div>
        </div>

        <div className="md:col-span-2">
          <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
            Signals to surface
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {WATCH_CATEGORIES.map((category) => {
              const on = watchCats.includes(category.key);
              return (
                <button
                  key={category.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleCat(category.key)}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border px-3.5 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    on
                      ? "border-primary bg-primary/5"
                      : "border-border bg-surface hover:bg-surface-alt",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border text-[10px]",
                      on ? "border-primary bg-primary text-[#fffdf8]" : "border-border",
                    )}
                  >
                    {on ? "✓" : ""}
                  </span>
                  <span>
                    <span className="block text-[13.5px] font-medium text-[var(--text-primary)]">
                      {category.label}
                    </span>
                    <span className="block text-[12px] text-[var(--text-muted)]">
                      {category.desc}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {saveError ? (
        <p className="mt-4 text-[12.5px] text-clay" role="alert">
          {saveError}
        </p>
      ) : null}

      {/* Footer */}
      <div className="mt-6 flex items-center justify-end gap-2">
        {editing && onCancel ? (
          <button type="button" className={GHOST_BUTTON} onClick={onCancel}>
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          className={PRIMARY_BUTTON}
          onClick={finish}
          disabled={saving || !canSave}
        >
          {saving ? "Saving…" : editing ? "Save changes" : "Finish setup"}
        </button>
      </div>
    </Card>
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
    const incoming = Array.from(list).filter((f) => f.size <= MAX_FILE_BYTES);
    const merged = [...files];
    for (const f of incoming) {
      if (!merged.some((m) => m.name === f.name && m.size === f.size)) {
        merged.push(f);
      }
    }
    onChange(merged);
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex min-h-36 w-full flex-col items-center justify-center gap-1.5 rounded-md border border-dashed px-3 py-4 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          dragging
            ? "border-primary bg-primary/5"
            : "border-input bg-card hover:bg-surface-alt",
        )}
      >
        <DocumentIcon size={20} className="text-brand-secondary" />
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          Drop files here
        </span>
        <span className="text-[11.5px] text-[var(--text-muted)]">
          or click to browse · PDF or text
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.doc,.docx,application/pdf,text/plain"
        className="hidden"
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
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
                onClick={() =>
                  onChange(files.filter((f) => f !== file))
                }
                className="shrink-0 text-[var(--text-muted)] hover:text-foreground"
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

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-[var(--text-primary)]">
        {label}
      </span>
      {children}
    </label>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
      {children}
    </h2>
  );
}

function Divider() {
  return <div className="my-6 border-t border-[var(--divider)]" />;
}
