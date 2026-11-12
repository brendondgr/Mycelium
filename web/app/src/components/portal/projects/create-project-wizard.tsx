"use client";

import * as React from "react";

import { ClusterOrganizer } from "@/components/onboarding/cluster-organizer";
import { CloseIcon } from "@/components/portal/icons";
import { usePortal } from "@/components/portal/portal-context";
import { composeClusters } from "@/lib/auth-client";
import type { ClusterGroup } from "@/lib/auth-types";
import { useCreateProject } from "@/lib/portal/hooks";
import { updateProjectState } from "@/lib/portal/mutations";
import { ProjectCapReachedError } from "@/lib/portal/mutations";
import type { MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";
import { canManageLab } from "@/lib/portal/nav";


type Scope = { kind: "personal" } | { kind: "lab"; slug: string; name: string };

/** Comma-separated free text into a clean list. The wizard's list fields. */
function splitList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function samesScope(a: Scope, b: Scope): boolean {
  if (a.kind === "personal" || b.kind === "personal") {
    return a.kind === b.kind;
  }
  return a.slug === b.slug;
}

/**
 * A guided "New project" modal: name + scope (step 1), then an optional
 * Mylo-composed research focus reviewed in the `ClusterOrganizer` (step 2).
 * Submits via `useCreateProject`; a plan-cap 403 surfaces inline instead of a
 * generic error. On success, offers to jump straight to the new project.
 */
export function CreateProjectWizard({ onClose }: { onClose: () => void }) {
  const { labs, currentLab, openProject } = usePortal();
  const managedLabs = React.useMemo(() => labs.filter(canManageLab), [labs]);

  const defaultScope: Scope = React.useMemo(() => {
    if (currentLab && canManageLab(currentLab)) {
      return { kind: "lab", slug: currentLab.slug, name: currentLab.name };
    }
    return { kind: "personal" };
  }, [currentLab]);

  const [step, setStep] = React.useState<1 | 2 | 3>(1);
  const [name, setName] = React.useState("");
  const [scope, setScope] = React.useState<Scope>(defaultScope);

  // Step 2 — the free-text description Mylo composes clusters from, and the
  // resulting (editable) focus. `hasFocus` toggles between the intro prompt
  // and the reviewable ClusterOrganizer.
  const [instruction, setInstruction] = React.useState("");
  const [composing, setComposing] = React.useState(false);
  const [composeError, setComposeError] = React.useState<string | null>(null);
  const [hasFocus, setHasFocus] = React.useState(false);
  const [focusAreas, setFocusAreas] = React.useState<string[]>([]);
  const [focusClusters, setFocusClusters] = React.useState<ClusterGroup[]>([]);
  const [watchTopics, setWatchTopics] = React.useState<string[]>([]);

  // Step 3 — the five questions that turn "a topic" into "a project" (plan 2.3).
  // Every one is optional: a wizard that refuses to finish until someone has
  // articulated their contribution collects nothing, and the state panel on the
  // project page asks the same questions whenever they are ready.
  const [problem, setProblem] = React.useState("");
  const [contribution, setContribution] = React.useState("");
  const [method, setMethod] = React.useState("");
  const [milestone, setMilestone] = React.useState("");
  const [milestoneDate, setMilestoneDate] = React.useState("");
  const [blocking, setBlocking] = React.useState("");

  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<{ id: string; name: string } | null>(
    null,
  );

  const create = useCreateProject();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const canContinue = name.trim().length > 0;

  async function handleCompose() {
    const text = instruction.trim();
    if (!text || composing) {
      return;
    }
    setComposeError(null);
    setComposing(true);
    try {
      const result = await composeClusters({
        instruction: text,
        clusters: [],
        areas: [],
        keywords: [],
        statement: text,
        watch_topics: [],
      });
      setFocusAreas(result.areas);
      setFocusClusters(result.clusters);
      setWatchTopics(result.watch_topics);
      setHasFocus(true);
    } catch (err) {
      setComposeError(
        err instanceof Error
          ? err.message
          : "Could not build a focus for this project. Try again, or skip.",
      );
    } finally {
      setComposing(false);
    }
  }

  function startOver() {
    setHasFocus(false);
    setFocusAreas([]);
    setFocusClusters([]);
    setWatchTopics([]);
    setComposeError(null);
  }

  function submit(withFocus: boolean) {
    if (create.isPending) {
      return;
    }
    setSubmitError(null);
    create.mutate(
      {
        name: name.trim(),
        labSlug: scope.kind === "lab" ? scope.slug : undefined,
        focus:
          withFocus && focusAreas.length > 0
            ? {
                areas: focusAreas,
                keywords: [],
                statement: instruction.trim(),
                clusters: focusClusters,
                watch_topics: watchTopics,
              }
            : undefined,
      },
      {
        onSuccess: (project) => {
          setCreated({ id: project.id, name: project.name });
          // Best-effort and after the fact: the project exists either way, and a
          // state save that fails must not read as "the project was not created".
          // The same questions are on the project page's state panel.
          void saveInitialState(project.id);
        },
        onError: (err) => {
          if (err instanceof ProjectCapReachedError) {
            setSubmitError(
              `You've reached the limit of ${err.cap} active project${
                err.cap === 1 ? "" : "s"
              } — archive one to add another.`,
            );
          } else {
            setSubmitError((err as Error).message);
          }
        },
      },
    );
  }

  async function saveInitialState(projectId: string) {
    const blockers = splitList(blocking).map((text) => ({ id: "", text }));
    const methods = splitList(method);
    const hasAnything =
      problem.trim() ||
      contribution.trim() ||
      methods.length ||
      milestone.trim() ||
      blockers.length;
    if (!hasAnything) return;
    try {
      await updateProjectState(projectId, {
        slow: {
          problem: problem.trim(),
          claimed_contribution: contribution.trim(),
          method: methods,
          blockers,
        },
        fast: milestone.trim()
          ? {
              milestones: [
                {
                  id: "",
                  kind: "results_by",
                  what: milestone.trim(),
                  date: milestoneDate,
                  source: "stated",
                },
              ],
            }
          : undefined,
      });
    } catch {
      // Swallowed on purpose — see the call site.
    }
  }

  const goToProject = () => {
    if (!created) return;
    openProject(created.id);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="New project"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-[var(--shadow)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-[var(--divider)] px-5 py-3.5">
          <div className="min-w-0">
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {created ? "Project created" : `Step ${step} of 3`}
            </p>
            <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">
              New project
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-full p-1 text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-secondary)]"
          >
            <CloseIcon size={15} />
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4">
          {created ? (
            <DoneStep name={created.name} hadFocus={hasFocus} onGo={goToProject} onClose={onClose} />
          ) : step === 1 ? (
            <StepName
              name={name}
              setName={setName}
              scope={scope}
              setScope={setScope}
              managedLabs={managedLabs}
            />
          ) : step === 2 ? (
            <StepFocus
              instruction={instruction}
              setInstruction={setInstruction}
              composing={composing}
              composeError={composeError}
              hasFocus={hasFocus}
              focusAreas={focusAreas}
              focusClusters={focusClusters}
              onCompose={handleCompose}
              onStartOver={startOver}
              onAreasChange={setFocusAreas}
              onClustersChange={setFocusClusters}
              onWatchSeed={setWatchTopics}
            />
          ) : (
            <StepState
              problem={problem}
              setProblem={setProblem}
              contribution={contribution}
              setContribution={setContribution}
              method={method}
              setMethod={setMethod}
              milestone={milestone}
              setMilestone={setMilestone}
              milestoneDate={milestoneDate}
              setMilestoneDate={setMilestoneDate}
              blocking={blocking}
              setBlocking={setBlocking}
            />
          )}

          {submitError ? (
            <p className="mt-3 text-[12.5px] text-clay" role="alert">
              {submitError}
            </p>
          ) : null}
        </div>

        {!created ? (
          <div className="flex items-center justify-between gap-2 border-t border-[var(--divider)] px-5 py-3.5">
            <button
              type="button"
              onClick={
                step === 1 ? onClose : () => setStep(step === 3 ? 2 : 1)
              }
              className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
            >
              {step === 1 ? "Cancel" : "Back"}
            </button>
            <div className="flex items-center gap-2">
              {step >= 2 ? (
                <button
                  type="button"
                  onClick={() => submit(hasFocus)}
                  disabled={create.isPending}
                  className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt disabled:opacity-50"
                >
                  {create.isPending
                    ? "Creating…"
                    : step === 2
                      ? "Skip — create without focus"
                      : "Skip — create without this"}
                </button>
              ) : null}
              <button
                type="button"
                onClick={() =>
                  step === 1
                    ? setStep(2)
                    : step === 2
                      ? setStep(3)
                      : submit(true)
                }
                disabled={
                  step === 1
                    ? !canContinue
                    : step === 2
                      ? !hasFocus
                      : create.isPending
                }
                className="rounded-full bg-primary px-3.5 py-1.5 text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] disabled:opacity-50"
              >
                {step === 1
                  ? "Continue"
                  : step === 2
                    ? "Continue"
                    : create.isPending
                      ? "Creating…"
                      : "Create project"}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ScopeChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-3 py-1.5 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "border-primary bg-primary text-[#fffdf8]"
          : "border-border bg-surface text-[var(--text-secondary)] hover:bg-surface-alt hover:text-[var(--text-primary)]",
      )}
    >
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        {label}
      </p>
      {children}
    </div>
  );
}

/** Step 1: name the project and pick where it lives. */
function StepName({
  name,
  setName,
  scope,
  setScope,
  managedLabs,
}: {
  name: string;
  setName: (value: string) => void;
  scope: Scope;
  setScope: (scope: Scope) => void;
  managedLabs: MyLab[];
}) {
  return (
    <div className="space-y-4">
      <Field label="Project name">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Robotic surgery literature review"
          aria-label="Project name"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </Field>

      <Field label="Where does this project live?">
        {managedLabs.length === 0 ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            Your personal workspace.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            <ScopeChip
              active={scope.kind === "personal"}
              onClick={() => setScope({ kind: "personal" })}
            >
              Personal
            </ScopeChip>
            {managedLabs.map((lab) => (
              <ScopeChip
                key={lab.slug}
                active={samesScope(scope, { kind: "lab", slug: lab.slug, name: lab.name })}
                onClick={() => setScope({ kind: "lab", slug: lab.slug, name: lab.name })}
              >
                {lab.name}
              </ScopeChip>
            ))}
          </div>
        )}
      </Field>
    </div>
  );
}

/** Step 2: an optional Mylo-composed research focus, reviewed/edited before
 * creating the project. */
/**
 * The five questions that turn a topic into a project (plan 2.3).
 *
 * The research focus on the step before decides what Mylo *searches for*. These
 * decide what it judges a result **against** — whether a preprint tests the same
 * question, whether a dataset closes a blocker, whether a venue's deadline is
 * reachable from the next milestone. Without them a report can only say what
 * exists on this topic, which is the thing every other tool already does.
 *
 * Every field is optional and the step is skippable. A wizard that will not
 * finish until someone has articulated their contribution collects nothing, and
 * the project page's state panel asks exactly these questions whenever the team
 * is ready to answer them.
 */
function StepState({
  problem,
  setProblem,
  contribution,
  setContribution,
  method,
  setMethod,
  milestone,
  setMilestone,
  milestoneDate,
  setMilestoneDate,
  blocking,
  setBlocking,
}: {
  problem: string;
  setProblem: (v: string) => void;
  contribution: string;
  setContribution: (v: string) => void;
  method: string;
  setMethod: (v: string) => void;
  milestone: string;
  setMilestone: (v: string) => void;
  milestoneDate: string;
  setMilestoneDate: (v: string) => void;
  blocking: string;
  setBlocking: (v: string) => void;
}) {
  const input =
    "w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  const label =
    "mb-1 block text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]";

  return (
    <div className="space-y-4">
      <p className="max-w-[58ch] text-[13.5px] leading-6 text-[var(--text-secondary)]">
        Optional, and you can fill these in later. They are what lets Mylo say
        whether a paper threatens your contribution or unblocks you, rather than
        only that it is on your topic.
      </p>

      <label className="block">
        <span className={label}>What problem is this project answering?</span>
        <textarea
          className={cn(input, "min-h-20 resize-y")}
          value={problem}
          onChange={(e) => setProblem(e.target.value)}
          placeholder="Whether multi-hop QA benchmarks can detect graph quality at all"
        />
      </label>

      <label className="block">
        <span className={label}>What is new about your answer?</span>
        <textarea
          className={cn(input, "min-h-20 resize-y")}
          value={contribution}
          onChange={(e) => setContribution(e.target.value)}
          placeholder="A measurement-validity study: config-diff ablations against retrieval error"
        />
      </label>

      <label className="block">
        <span className={label}>Method and data</span>
        <input
          className={input}
          value={method}
          onChange={(e) => setMethod(e.target.value)}
          placeholder="Comma-separated — multi-lens extraction, schema settling, MuSiQue"
        />
      </label>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[2fr_1fr]">
        <label className="block">
          <span className={label}>Next milestone</span>
          <input
            className={input}
            value={milestone}
            onChange={(e) => setMilestone(e.target.value)}
            placeholder="50-passage pilot results"
          />
        </label>
        <label className="block">
          <span className={label}>By when</span>
          <input
            type="date"
            className={input}
            value={milestoneDate}
            onChange={(e) => setMilestoneDate(e.target.value)}
          />
        </label>
      </div>

      <label className="block">
        <span className={label}>What is blocking you?</span>
        <input
          className={input}
          value={blocking}
          onChange={(e) => setBlocking(e.target.value)}
          placeholder="Comma-separated — no labeled evaluation set, single rater"
        />
      </label>
    </div>
  );
}

function StepFocus({
  instruction,
  setInstruction,
  composing,
  composeError,
  hasFocus,
  focusAreas,
  focusClusters,
  onCompose,
  onStartOver,
  onAreasChange,
  onClustersChange,
  onWatchSeed,
}: {
  instruction: string;
  setInstruction: (value: string) => void;
  composing: boolean;
  composeError: string | null;
  hasFocus: boolean;
  focusAreas: string[];
  focusClusters: ClusterGroup[];
  onCompose: () => void;
  onStartOver: () => void;
  onAreasChange: (areas: string[]) => void;
  onClustersChange: (clusters: ClusterGroup[]) => void;
  onWatchSeed: (topics: string[]) => void;
}) {
  if (hasFocus) {
    return (
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <p className="text-[12.5px] text-[var(--text-secondary)]">
            Mylo built a focus from your description. Review it below — rename,
            merge, or add topics — then create the project.
          </p>
          <button
            type="button"
            onClick={onStartOver}
            className="shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-[12px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
          >
            Start over
          </button>
        </div>
        <ClusterOrganizer
          areas={focusAreas}
          clusters={focusClusters}
          onChange={onClustersChange}
          onAreasChange={onAreasChange}
          onWatchSeed={onWatchSeed}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Field label="What is this project about? What is its purpose?">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          rows={4}
          placeholder="e.g. A review of robotic surgery platforms and VLA models applied to surgical assistance."
          className="w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </Field>
      <p className="text-[12px] text-[var(--text-secondary)]">
        Mylo will build a themed research focus for this project — areas,
        clusters, and watch topics it can search on. You can review and edit
        the result before creating the project, or skip this and add a focus
        later.
      </p>
      {composeError ? (
        <p className="text-[12.5px] text-clay" role="alert">
          {composeError}
        </p>
      ) : null}
      <div>
        <button
          type="button"
          onClick={onCompose}
          disabled={composing || instruction.trim() === ""}
          className="rounded-full bg-primary px-3.5 py-1.5 text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)] disabled:opacity-50"
        >
          {composing ? "Building…" : "Build focus with Mylo"}
        </button>
      </div>
    </div>
  );
}

/** The post-create confirmation screen. */
function DoneStep({
  name,
  hadFocus,
  onGo,
  onClose,
}: {
  name: string;
  hadFocus: boolean;
  onGo: () => void;
  onClose: () => void;
}) {
  return (
    <div className="space-y-3 text-center">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        &ldquo;{name}&rdquo; is ready.
      </p>
      <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
        {hadFocus
          ? "Mylo is researching this project's focus in the background — papers, grants, fellowships, and conferences will start appearing shortly."
          : "Add a research focus any time from the project's settings so Mylo can start finding matches for it."}
      </p>
      <div className="flex items-center justify-center gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[13px] font-semibold text-[var(--text-secondary)] hover:bg-surface-alt"
        >
          Close
        </button>
        <button
          type="button"
          onClick={onGo}
          className="rounded-full bg-primary px-3.5 py-1.5 text-[13px] font-semibold text-[#fffdf8] hover:bg-[var(--brand-primary-hover)]"
        >
          Go to project
        </button>
      </div>
    </div>
  );
}
