"use client";

import * as React from "react";

import { MyloMark } from "@/components/brand/mylo-mark";
import { Chip, TokenField, dedupe, inputClass } from "@/components/onboarding/fields";
import { Card } from "@/components/portal/primitives/card";
import {
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
  { id: "realtime", label: "Real-time" },
];

const STEP_LABELS = ["Purpose & focus", "What Milo watches", "Review & finish"];

const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/** Prefilled values for editing an already-configured lab. */
export type LabOnboardingInitial = {
  statement: string;
  areas: string[];
  keywords: string[];
  watchTopics: string[];
  watchCats: string[];
  cadence: WatchCadence;
};

/**
 * Inline lab onboarding, shown on the lab overview when a lab has no profile
 * yet, or re-opened in edit mode to fix an existing lab. It captures the lab's
 * purpose (statement), research focus (areas), and tags (keywords) — optionally
 * drafted from the PI's description plus pasted source material by the LLM —
 * then what Milo watches, and saves both the lab profile and its watch
 * settings. Modeled on the personal onboarding flow.
 *
 * In edit mode the parent renders this only once its profile/watch queries have
 * settled and passes ``initial`` so state can be lazily seeded without an
 * effect (avoids the set-state-in-effect lint rule).
 */
export function LabOnboarding({
  lab,
  mode = "create",
  initial,
  onDone,
  onCancel,
}: {
  lab: MyLab;
  mode?: "create" | "edit";
  initial?: LabOnboardingInitial;
  onDone?: () => void;
  onCancel?: () => void;
}) {
  const synthesize = useSynthesizeLabProfile(lab.slug);
  const saveProfile = useUpdateLabProfile(lab.slug);
  const saveWatch = useUpdateLabWatch(lab.slug);

  const [step, setStep] = React.useState(0);

  // Step 1 — purpose & focus (+ optional source material for the LLM).
  const [description, setDescription] = React.useState("");
  const [statement, setStatement] = React.useState(initial?.statement ?? "");
  const [areas, setAreas] = React.useState<string[]>(initial?.areas ?? []);
  const [keywords, setKeywords] = React.useState<string[]>(
    initial?.keywords ?? [],
  );
  const [sourceText, setSourceText] = React.useState("");
  const [synthError, setSynthError] = React.useState<string | null>(null);
  const [synthNote, setSynthNote] = React.useState<string | null>(null);

  // Step 2 — what Milo watches.
  const [watchTopics, setWatchTopics] = React.useState<string[]>(
    initial?.watchTopics ?? [],
  );
  const [watchCats, setWatchCats] = React.useState<string[]>(
    initial?.watchCats ?? ["papers", "grants", "conferences"],
  );
  const [cadence, setCadence] = React.useState<WatchCadence>(
    initial?.cadence ?? "weekly",
  );

  const [saveError, setSaveError] = React.useState<string | null>(null);
  const editing = mode === "edit";

  function runSynthesis() {
    setSynthError(null);
    setSynthNote(null);
    synthesize.mutate(
      { description, areas, source_text: sourceText },
      {
        onSuccess: (result) => {
          if (result.statement) setStatement(result.statement);
          if (result.areas?.length) setAreas(dedupe(result.areas));
          if (result.keywords?.length) setKeywords(dedupe(result.keywords));
          setSynthNote("Mylo drafted a profile below — edit anything before continuing.");
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

  function goWatch() {
    // Seed watch topics from the lab's focus + tags when the user hasn't set any.
    if (watchTopics.length === 0) {
      setWatchTopics(dedupe([...areas, ...keywords]).slice(0, 12));
    }
    setStep(1);
  }

  function finish() {
    setSaveError(null);
    const cleanAreas = dedupe(areas);
    const cleanKeywords = dedupe(keywords);
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
          {
            topics: dedupe(watchTopics),
            categories: watchCats,
            cadence,
          },
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
  const canContinueStep1 = statement.trim().length > 0 || areas.length > 0;

  return (
    <Card accent="primary-rule" className="p-6">
      {/* Header */}
      <div className="mb-5 flex items-start gap-3">
        <MyloMark className="mt-0.5 h-9 w-9 shrink-0" />
        <div>
          <h2 className="font-serif text-[22px] font-semibold leading-tight text-[var(--text-primary)]">
            {editing ? `Edit ${lab.name}` : `Set up ${lab.name}`}
          </h2>
          <p className="mt-1 text-[13.5px] text-[var(--text-secondary)]">
            Tell Mylo what this lab works on. This is what lets paper, grant, and
            conference matching understand the lab&apos;s purpose later.
          </p>
        </div>
      </div>

      {/* Step indicator */}
      <ol className="mb-5 flex flex-wrap gap-x-4 gap-y-1" aria-label="Onboarding steps">
        {STEP_LABELS.map((labelText, i) => (
          <li
            key={labelText}
            aria-current={i === step ? "step" : undefined}
            className={cn(
              "flex items-center gap-1.5 text-[12.5px] font-medium",
              i === step
                ? "text-[var(--text-primary)]"
                : i < step
                  ? "text-primary"
                  : "text-[var(--text-muted)]",
            )}
          >
            <span
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-full text-[11px]",
                i <= step ? "bg-primary text-[#fffdf8]" : "bg-surface-alt",
              )}
            >
              {i + 1}
            </span>
            {labelText}
          </li>
        ))}
      </ol>

      {/* Step body */}
      {step === 0 ? (
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-[13px] font-medium text-[var(--text-primary)]">
              Describe the lab in a sentence or two
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="e.g. We study coral-reef resilience under ocean warming, combining remote sensing with machine learning."
              className={cn(inputClass, "min-h-20 resize-y py-2")}
            />
          </label>

          <details className="rounded-md border border-border bg-surface-alt/50 px-3 py-2">
            <summary className="cursor-pointer text-[13px] font-medium text-[var(--text-secondary)]">
              Add source material for Mylo (optional)
            </summary>
            <p className="mt-2 text-[12px] text-[var(--text-muted)]">
              Paste representative paper titles or abstracts, members&apos;
              profiles, or portfolio blurbs. Mylo reads them to draft the lab
              profile more accurately.
            </p>
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              rows={4}
              placeholder="Paste titles, abstracts, or member bios here…"
              className={cn(inputClass, "mt-2 min-h-24 resize-y py-2")}
            />
          </details>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={GHOST_BUTTON}
              onClick={runSynthesis}
              disabled={
                synthesize.isPending ||
                (!description.trim() && !sourceText.trim() && areas.length === 0)
              }
            >
              {synthesize.isPending ? "Mylo is drafting…" : "✨ Draft with Mylo"}
            </button>
            <span className="text-[12px] text-[var(--text-muted)]">
              Optional — you can also fill everything in by hand.
            </span>
          </div>
          {synthNote ? (
            <p className="text-[12.5px] text-primary">{synthNote}</p>
          ) : null}
          {synthError ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {synthError}
            </p>
          ) : null}

          <label className="block">
            <span className="mb-1 block text-[13px] font-medium text-[var(--text-primary)]">
              Statement of purpose
            </span>
            <textarea
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              rows={3}
              placeholder="The lab's shared research purpose."
              className={cn(inputClass, "min-h-20 resize-y py-2")}
            />
          </label>

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

          <div className="flex justify-between pt-1">
            {editing && onCancel ? (
              <button type="button" className={GHOST_BUTTON} onClick={onCancel}>
                Cancel
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              className={PRIMARY_BUTTON}
              onClick={goWatch}
              disabled={!canContinueStep1}
            >
              Continue
            </button>
          </div>
        </div>
      ) : step === 1 ? (
        <div className="space-y-4">
          <TokenField
            label="Topics Milo monitors for the lab"
            items={watchTopics}
            onChange={setWatchTopics}
            placeholder="Add a topic, press Enter"
          />

          <div>
            <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
              Signals to surface
            </p>
            <div className="space-y-2">
              {WATCH_CATEGORIES.map((category) => {
                const on = watchCats.includes(category.key);
                return (
                  <button
                    key={category.key}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleCat(category.key)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-xl border px-3.5 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      on
                        ? "border-primary bg-primary/5"
                        : "border-border bg-surface hover:bg-surface-alt",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border text-[10px]",
                        on
                          ? "border-primary bg-primary text-[#fffdf8]"
                          : "border-border",
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

          <div className="flex justify-between pt-1">
            <button type="button" className={GHOST_BUTTON} onClick={() => setStep(0)}>
              Back
            </button>
            <button type="button" className={PRIMARY_BUTTON} onClick={() => setStep(2)}>
              Continue
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <ReviewRow label="Statement">
            {statement.trim() ? (
              <p className="text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
                {statement}
              </p>
            ) : (
              <Muted>No statement yet.</Muted>
            )}
          </ReviewRow>
          <ReviewRow label="Focus areas">
            <ChipList items={areas} />
          </ReviewRow>
          <ReviewRow label="Tags & keywords">
            <ChipList items={keywords} />
          </ReviewRow>
          <ReviewRow label="Milo watches">
            <ChipList items={watchTopics} />
            <p className="mt-1 text-[12px] text-[var(--text-muted)]">
              {watchCats.length} signal type{watchCats.length === 1 ? "" : "s"} ·{" "}
              {CADENCES.find((c) => c.id === cadence)?.label}
            </p>
          </ReviewRow>

          {saveError ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {saveError}
            </p>
          ) : null}

          <div className="flex justify-between pt-1">
            <button type="button" className={GHOST_BUTTON} onClick={() => setStep(1)}>
              Back
            </button>
            <button
              type="button"
              className={PRIMARY_BUTTON}
              onClick={finish}
              disabled={saving}
            >
              {saving ? "Saving…" : editing ? "Save changes" : "Finish setup"}
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

function ReviewRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
        {label}
      </p>
      {children}
    </div>
  );
}

function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <Muted>None added.</Muted>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className="inline-flex items-center rounded-full border border-border bg-surface-alt px-2.5 py-1 text-[12.5px] text-[var(--text-secondary)]"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-[13px] text-[var(--text-muted)]">{children}</p>;
}
