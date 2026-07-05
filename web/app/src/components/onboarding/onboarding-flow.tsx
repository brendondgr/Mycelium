"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { MyloMark } from "@/components/brand/mylo-mark";
import MyceliumBranch from "@/components/onboarding/mycelium-branch";
import OnboardingStage from "@/components/onboarding/onboarding-stage";
import ProfileSynthesisProgress, {
  type SynthesisStage,
} from "@/components/onboarding/profile-synthesis-progress";
import {
  Chip,
  TokenField,
  dedupe,
  inputClass,
} from "@/components/onboarding/fields";
import {
  confirmInterests,
  getWatch,
  saveProfileBasics,
  saveWatch,
  synthesizeProfile,
  verifyEmail,
} from "@/lib/auth-client";
import { fetchProfile } from "@/lib/portal/client";
import type {
  ResearchInterests,
  ResearchSource,
  WatchCadence,
} from "@/lib/auth-types";
import { cn } from "@/lib/utils";

const ROLES = [
  { label: "Student", value: "student" },
  { label: "Postdoc", value: "postdoc" },
  { label: "Researcher", value: "researcher" },
  { label: "Principal Investigator", value: "pi" },
  { label: "Staff Scientist", value: "staff" },
];

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

const WATCH_CATEGORIES = [
  { key: "papers", label: "New papers & preprints", desc: "Relevant to your areas and keywords." },
  { key: "grants", label: "Grant deadlines", desc: "Funding that fits your profile." },
  { key: "fellowships", label: "Fellowships", desc: "Matched to your stage and timeline." },
  { key: "collaborators", label: "Potential collaborators", desc: "People on adjacent problems." },
  { key: "retractions", label: "Retractions & corrections", desc: "When work you cited changes." },
  { key: "graph", label: "Knowledge-graph updates", desc: "New connections across your network." },
];

const CADENCES: { id: WatchCadence; label: string }[] = [
  { id: "daily", label: "Daily digest" },
  { id: "weekly", label: "Weekly digest" },
  { id: "realtime", label: "Real-time" },
];

const STEP_LABELS = [
  "About you",
  "Import your research",
  "Review profile",
  "What Milo watches",
];

const MAX_RESUME_BYTES = 5 * 1024 * 1024;
const DEMO_CODE = ["4", "8", "2", "9", "1", "3"];

// Minimum time each early synthesis stage is shown so the user can read the
// narration even when the request returns quickly. The final (language-model)
// stage is held open until the real request resolves.
const SYNTH_STAGE_MS = 850;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

type OnboardingFlowProps = {
  email: string;
  /**
   * "onboard" is the first-run gate (starts on email verify, ends in the
   * workspace). "edit" re-enters the same flow from the profile page,
   * prefilled with the user's saved answers, and returns there on save.
   */
  mode?: "onboard" | "edit";
};

export function OnboardingFlow({ email, mode = "onboard" }: OnboardingFlowProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const editing = mode === "edit";
  const [screen, setScreen] = useState<
    "verify" | "intake" | "synthesizing" | "building"
  >(editing ? "intake" : "verify");
  // Edit mode prefills from the saved profile; gate the form until it loads.
  const [hydrated, setHydrated] = useState(!editing);
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);

  // Step 0 — about you
  const [role, setRole] = useState("researcher");
  const [institution, setInstitution] = useState("");

  // Step 1 — import
  const [source, setSource] = useState<ResearchSource | "">("");
  const [identifier, setIdentifier] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeName, setResumeName] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [imported, setImported] = useState(false);
  const [synthStages, setSynthStages] = useState<SynthesisStage[]>([]);
  const [synthStage, setSynthStage] = useState(0);
  const [synthDone, setSynthDone] = useState(false);

  // Step 2 — review (research interests)
  const [statement, setStatement] = useState("");
  const [areas, setAreas] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [draftSources, setDraftSources] = useState<Record<string, unknown>>({});

  // Step 3 — watch
  const [watchTopics, setWatchTopics] = useState<string[]>([]);
  const [watchCats, setWatchCats] = useState<Record<string, boolean>>({
    papers: true,
    grants: true,
    fellowships: true,
    collaborators: false,
    retractions: false,
    graph: true,
  });
  const [cadence, setCadence] = useState<WatchCadence>("weekly");

  // Verify (scaffold)
  const [code, setCode] = useState<string[]>(["", "", "", "", "", ""]);
  const [verifyError, setVerifyError] = useState("");
  const [verifyResent, setVerifyResent] = useState(false);
  const codeRefs = useRef<Array<HTMLInputElement | null>>([]);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sourceOption = SOURCES.find((option) => option.value === source) ?? null;
  const hasImportInput = Boolean((source && identifier.trim()) || resumeFile);

  function goStep(target: number, dir: number) {
    setDirection(dir);
    setStep(target);
    window.scrollTo(0, 0);
  }

  function applyInterests(interests: ResearchInterests) {
    setStatement(interests.statement ?? "");
    setAreas(interests.areas ?? []);
    setKeywords(interests.keywords ?? []);
    setSkills(interests.skills ?? []);
    setDraftSources(interests.sources ?? {});
    const seed = dedupe([
      ...(interests.areas ?? []),
      ...(interests.keywords ?? []),
    ]).slice(0, 12);
    setWatchTopics((prev) => (prev.length ? prev : seed));
  }

  // -- edit prefill --------------------------------------------------------
  // In edit mode, load the saved profile + watch settings once and seed the
  // form so the user revises what is already there rather than starting blank.
  useEffect(() => {
    if (!editing) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [profile, watch] = await Promise.all([
          fetchProfile(),
          getWatch().catch(() => null),
        ]);
        if (cancelled) {
          return;
        }
        if (ROLES.some((option) => option.value === profile.academic_title)) {
          setRole(profile.academic_title);
        }
        setInstitution(profile.institution ?? "");
        const interests = profile.interests;
        if (interests) {
          setStatement(interests.statement ?? "");
          setAreas(interests.areas ?? []);
          setKeywords(interests.keywords ?? []);
          setSkills(interests.skills ?? []);
          setDraftSources(interests.sources ?? {});
        }
        if (watch) {
          setWatchTopics(watch.topics ?? []);
          setWatchCats(
            WATCH_CATEGORIES.reduce<Record<string, boolean>>((acc, category) => {
              acc[category.key] = watch.categories.includes(category.key);
              return acc;
            }, {}),
          );
          setCadence(watch.cadence ?? "weekly");
        }
      } catch {
        // Leave the form at its defaults; the user can still fill it in.
      } finally {
        if (!cancelled) {
          setHydrated(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editing]);

  // -- verify --------------------------------------------------------------
  async function verifyAndContinue() {
    if (code.some((digit) => digit === "")) {
      setVerifyError("Enter all 6 digits, or skip for now.");
      return;
    }
    setVerifyError("");
    setBusy(true);
    try {
      await verifyEmail();
    } catch {
      // Verification is non-blocking — proceed regardless (scaffold).
    } finally {
      setBusy(false);
    }
    enterIntake();
  }

  function enterIntake() {
    setScreen("intake");
    setStep(0);
    setDirection(1);
    window.scrollTo(0, 0);
  }

  // -- import --------------------------------------------------------------
  function onResumeChange(file: File | null) {
    setImportError(null);
    if (!file) {
      setResumeFile(null);
      setResumeName("");
      return;
    }
    if (file.size > MAX_RESUME_BYTES) {
      setImportError("That file is larger than 5 MB. Try a smaller one.");
      return;
    }
    setResumeFile(file);
    setResumeName(file.name);
  }

  // The narrated stages mirror the real synthesize pipeline and adapt to what
  // the user actually provided (a source, a résumé, or both).
  function buildSynthStages(): SynthesisStage[] {
    const stages: SynthesisStage[] = [];
    if (sourceOption) {
      stages.push({
        label: `Reading your most-cited and recent work on ${sourceOption.label}`,
      });
      stages.push({ label: "Gathering abstracts and key passages" });
    }
    if (resumeFile) {
      stages.push({ label: "Reading your résumé" });
    }
    stages.push({ label: "Asking the language model to synthesize it all" });
    stages.push({
      label: "Drafting your statement, areas, keywords, and skills",
    });
    return stages;
  }

  async function runImport() {
    setImportError(null);
    if (!hasImportInput) {
      goStep(2, 1); // nothing to import — fall through to manual entry
      return;
    }

    const stages = buildSynthStages();
    const lastStage = stages.length - 1;
    setSynthStages(stages);
    setSynthStage(0);
    setSynthDone(false);
    setImporting(true);
    setScreen("synthesizing");
    window.scrollTo(0, 0);

    // Start the real request immediately; settle it into a result object so a
    // fast failure during the timed walk never surfaces as an unhandled
    // rejection.
    const settled = synthesizeProfile({
      source: source || undefined,
      identifier: identifier.trim() || undefined,
      resume: resumeFile,
    }).then(
      (value) => ({ ok: true as const, value }),
      (error) => ({ ok: false as const, error }),
    );

    // Walk through the early stages on a timer, then hold on the final stage
    // until the language model actually returns.
    for (let index = 0; index < lastStage; index += 1) {
      setSynthStage(index);
      await wait(SYNTH_STAGE_MS);
    }
    setSynthStage(lastStage);

    const result = await settled;
    setImporting(false);

    if (result.ok) {
      applyInterests(result.value.interests);
      setImported(true);
      setSynthDone(true);
      await wait(650); // let the completed checklist register
      setScreen("intake");
      goStep(2, 1);
      return;
    }

    // Surface the failure back on the import step.
    setScreen("intake");
    setStep(1);
    setImportError(
      result.error instanceof Error
        ? result.error.message
        : "Could not build your profile. Try again.",
    );
  }

  // -- navigation ----------------------------------------------------------
  const reviewBlocked = step === 2 && areas.length < 1;

  function primaryAction() {
    if (step === 0) {
      goStep(1, 1);
      return;
    }
    if (step === 1) {
      void runImport();
      return;
    }
    if (step === 2) {
      if (reviewBlocked) {
        return;
      }
      goStep(3, 1);
      return;
    }
    void finish();
  }

  function back() {
    if (step > 0) {
      goStep(step - 1, -1);
    } else if (editing) {
      // Step 0 in edit mode has no verify screen behind it — leave the flow.
      router.push("/app/profile");
    } else {
      setScreen("verify");
    }
  }

  function primaryLabel(): string {
    if (step === 1) {
      return importing ? "Growing…" : hasImportInput ? "Grow my profile" : "Continue";
    }
    if (step === 3) {
      if (editing) {
        return busy ? "Saving…" : "Save changes";
      }
      return "Enter Mycelium";
    }
    return "Continue";
  }

  async function finish() {
    setSubmitError(null);
    const interests: ResearchInterests = { version: 1, areas };
    if (statement.trim()) {
      interests.statement = statement.trim();
    }
    if (keywords.length) {
      interests.keywords = keywords;
    }
    if (skills.length) {
      interests.skills = skills;
    }
    if (Object.keys(draftSources).length) {
      interests.sources = draftSources;
    }

    const categories = WATCH_CATEGORIES.filter((c) => watchCats[c.key]).map(
      (c) => c.key,
    );

    const saves = (): Promise<unknown>[] => [
      saveProfileBasics({
        academic_title: role,
        ...(institution.trim() ? { institution: institution.trim() } : {}),
      }),
      confirmInterests(interests),
      saveWatch({ topics: watchTopics, categories, cadence }),
    ];

    // Edit mode: save in place and return to the profile with fresh data —
    // no first-run "weaving" animation, no jump to the overview.
    if (editing) {
      setBusy(true);
      try {
        await Promise.all(saves());
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["portal", "profile"] }),
          queryClient.invalidateQueries({ queryKey: ["portal", "watch"] }),
        ]);
        router.push("/app/profile");
        router.refresh();
      } catch (error) {
        setBusy(false);
        setSubmitError(
          error instanceof Error
            ? error.message
            : "Could not save your changes. Try again.",
        );
      }
      return;
    }

    setScreen("building");
    try {
      await Promise.all([...saves(), wait(1400)]);
      router.replace("/app/overview");
      router.refresh();
    } catch (error) {
      setScreen("intake");
      setStep(3);
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Could not save your answers. Try again.",
      );
    }
  }

  // -- edit prefill loading ------------------------------------------------
  if (editing && !hydrated) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
        <MyloMark className="mylo-float h-14 w-[50px]" />
        <p className="text-sm text-[var(--text-secondary)]">
          Loading your profile…
        </p>
      </div>
    );
  }

  // -- synthesizing --------------------------------------------------------
  if (screen === "synthesizing") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center">
        <ProfileSynthesisProgress
          stages={synthStages}
          active={synthStage}
          done={synthDone}
        />
      </div>
    );
  }

  // -- building ------------------------------------------------------------
  if (screen === "building") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
        <div className="relative h-[200px] w-[240px]">
          <svg viewBox="0 0 240 200" className="absolute inset-0 h-full w-full">
            <g stroke="var(--brand-secondary)" strokeWidth="1.6" fill="none">
              <path d="M120 110 L54 56" />
              <path d="M120 110 L196 60" />
              <path d="M120 110 L40 150" />
              <path d="M120 110 L200 148" />
              <path d="M120 110 L120 30" />
            </g>
            <g>
              <circle cx="54" cy="56" r="6" fill="var(--primary)" className="motion-safe:animate-pulse" />
              <circle cx="196" cy="60" r="6" fill="var(--brand-accent)" className="motion-safe:animate-pulse" />
              <circle cx="40" cy="150" r="6" fill="var(--brand-secondary)" className="motion-safe:animate-pulse" />
              <circle cx="200" cy="148" r="6" fill="var(--primary)" className="motion-safe:animate-pulse" />
              <circle cx="120" cy="30" r="6" fill="var(--brand-accent)" className="motion-safe:animate-pulse" />
            </g>
          </svg>
          <div className="absolute left-1/2 top-[55%] h-[82px] w-[74px] -translate-x-1/2 -translate-y-1/2">
            <MyloMark className="mylo-float h-full w-full" />
          </div>
        </div>
        <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
          Weaving your knowledge graph…
        </h2>
        <p className="max-w-sm text-[var(--text-secondary)]">
          Seeding {areas[0] ?? "your interests"} and queuing your first scan.
        </p>
      </div>
    );
  }

  // -- verify --------------------------------------------------------------
  if (screen === "verify") {
    return (
      <div className="mx-auto w-full max-w-md text-center">
        <MyloMark className="mylo-float mx-auto mb-4 h-16 w-[58px]" />
        <h1 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
          Check your inbox
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          We sent a 6-digit verification code to
        </p>
        <p className="font-medium text-[var(--text-primary)]">{email}</p>

        <div className="mt-6 flex justify-center gap-2">
          {code.map((digit, index) => (
            <input
              key={index}
              ref={(el) => {
                codeRefs.current[index] = el;
              }}
              value={digit}
              inputMode="numeric"
              maxLength={1}
              aria-label={`Digit ${index + 1}`}
              onChange={(event) => {
                const value = event.target.value.replace(/\D/g, "").slice(-1);
                setCode((prev) => {
                  const nextCode = [...prev];
                  nextCode[index] = value;
                  return nextCode;
                });
                setVerifyError("");
                if (value && index < 5) {
                  codeRefs.current[index + 1]?.focus();
                }
              }}
              onKeyDown={(event) => {
                if (
                  event.key === "Backspace" &&
                  !event.currentTarget.value &&
                  index > 0
                ) {
                  codeRefs.current[index - 1]?.focus();
                }
              }}
              className="h-14 w-12 rounded-xl border border-border bg-surface text-center font-serif text-2xl font-semibold text-foreground outline-none transition focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20"
            />
          ))}
        </div>

        {verifyError ? (
          <p className="mt-3 text-sm text-destructive" role="alert">
            {verifyError}
          </p>
        ) : null}

        <Button
          className="mx-auto mt-6 w-full max-w-xs rounded-full"
          size="lg"
          disabled={busy}
          onClick={() => void verifyAndContinue()}
        >
          {busy ? "Verifying…" : "Verify & continue"}
        </Button>

        <div className="mt-4 min-h-5 text-sm text-[var(--text-muted)]">
          {verifyResent ? (
            <span className="font-medium text-primary">
              Code re-sent — check your inbox.
            </span>
          ) : (
            <span>
              Didn&rsquo;t get it?{" "}
              <button
                type="button"
                className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => setVerifyResent(true)}
              >
                Resend code
              </button>
            </span>
          )}
        </div>

        <div className="mt-5 flex items-center justify-center gap-4 border-t border-[var(--divider)] pt-4 text-sm">
          <button
            type="button"
            className="font-medium text-brand-secondary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setCode(DEMO_CODE)}
          >
            Fill demo code
          </button>
          <span className="text-[var(--text-muted)]" aria-hidden="true">
            |
          </span>
          <button
            type="button"
            className="text-[var(--text-muted)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={enterIntake}
          >
            Skip for now
          </button>
        </div>
        <p className="mt-4 text-xs text-[var(--text-muted)]">
          Verification is optional right now — you&rsquo;re signed in either way
          and can confirm later from Settings.
        </p>
      </div>
    );
  }

  // -- intake panels -------------------------------------------------------
  const cardClass =
    "rounded-2xl border border-border bg-card p-6 shadow-[0_12px_34px_-22px_rgba(70,80,50,0.45)] sm:p-8";

  const panelAbout = (
    <div className={cardClass}>
      <div className="space-y-6">
        <div>
          <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            First, tell us about you
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            This calibrates how Mylo weights papers and opportunities.
          </p>
        </div>
        <div className="space-y-3">
          <p className="text-sm font-medium text-[var(--text-primary)]">Your role</p>
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
        <div className="space-y-2">
          <label
            className="text-sm font-medium text-[var(--text-primary)]"
            htmlFor="institution"
          >
            Institution{" "}
            <span className="text-[var(--text-muted)]">(optional)</span>
          </label>
          <input
            id="institution"
            type="text"
            value={institution}
            onChange={(event) => setInstitution(event.target.value)}
            className={inputClass}
          />
        </div>
      </div>
    </div>
  );

  const panelImport = (
    <div className={cardClass}>
      <div className="space-y-5">
        <div>
          <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            Let Mylo build your research profile
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Pick one source and Mylo reads your most-cited and most-recent work.
            Add a résumé too, if you like — you can edit everything next.
          </p>
        </div>

        <div className="space-y-3">
          <p className="text-sm font-medium text-[var(--text-primary)]">
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
                  <span className="block text-sm font-semibold text-[var(--text-primary)]">
                    {option.label}
                  </span>
                  <span className="mt-1 block text-xs text-[var(--text-muted)]">
                    {option.tagline}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {sourceOption ? (
          <div className="space-y-2">
            <label
              className="text-sm font-medium text-[var(--text-primary)]"
              htmlFor="author-id"
            >
              {sourceOption.idLabel}
            </label>
            <input
              id="author-id"
              type="text"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder={sourceOption.placeholder}
              className={inputClass}
            />
            <p className="text-xs text-[var(--text-muted)]">{sourceOption.help}</p>
          </div>
        ) : null}

        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Upload a résumé or CV{" "}
            <span className="text-[var(--text-muted)]">(optional)</span>
          </p>
          <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-card px-4 py-3 text-sm transition hover:border-brand-secondary focus-within:ring-2 focus-within:ring-ring">
            <span className={resumeName ? "text-foreground" : "text-[var(--text-muted)]"}>
              {resumeName || "Choose a PDF or text file"}
            </span>
            <span className="rounded-full border border-border px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
              Browse
            </span>
            <input
              type="file"
              accept=".pdf,.txt,.text,.md,.markdown,text/plain,application/pdf"
              className="sr-only"
              onChange={(event) =>
                onResumeChange(event.target.files?.[0] ?? null)
              }
            />
          </label>
          {resumeName ? (
            <button
              type="button"
              onClick={() => onResumeChange(null)}
              className="text-xs font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
            >
              Remove file
            </button>
          ) : null}
          <p className="text-xs text-[var(--text-muted)]">
            Mylo reads it to draft your interests, then discards the file.
          </p>
        </div>

        {importError ? (
          <p
            className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {importError}
          </p>
        ) : null}

        <button
          type="button"
          onClick={() => goStep(2, 1)}
          className="text-sm font-medium text-brand-secondary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Skip — I&rsquo;ll add my interests manually
        </button>
      </div>
    </div>
  );

  const panelReview = (
    <div className={cardClass}>
      <div className="space-y-5">
        <div>
          <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            Review your research profile
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {imported
              ? "Mylo drafted this from your sources. Edit anything — add or remove freely."
              : "Add your research interests below. A statement and a few areas are enough to start."}
          </p>
        </div>

        <div className="space-y-2">
          <label
            className="text-sm font-medium text-[var(--text-primary)]"
            htmlFor="statement"
          >
            Research statement
          </label>
          <textarea
            id="statement"
            value={statement}
            onChange={(event) => setStatement(event.target.value)}
            placeholder="A sentence or two about what you research and how."
            className={cn(inputClass, "min-h-28 py-3 leading-relaxed")}
          />
        </div>

        <TokenField
          label="Research areas"
          items={areas}
          onChange={setAreas}
          placeholder="Add an area and press Enter"
        />
        {areas.length < 1 ? (
          <p className="text-xs text-destructive">
            Add at least one research area to continue.
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
        <p className="text-xs text-[var(--text-muted)]">
          Your semantic fingerprint — Mylo uses these to find and rank papers.
        </p>

        <TokenField
          label="Skills"
          items={skills}
          onChange={setSkills}
          placeholder="Add a skill and press Enter"
        />
        <p className="text-xs text-[var(--text-muted)]">
          Saved for future fellowship matching. Not used for search yet.
        </p>
      </div>
    </div>
  );

  const panelWatch = (
    <div className={cardClass}>
      <div className="space-y-5">
        <div>
          <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            What should Mylo keep an eye on?
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            These topics are exactly what Mylo searches for when scanning for new
            papers — they&rsquo;re the only thing that drives your literature
            search. They were seeded from your interests; add or remove anything.
          </p>
        </div>

        <TokenField
          label="Watch topics"
          items={watchTopics}
          onChange={setWatchTopics}
          placeholder="Add a topic and press Enter"
        />

        <div className="space-y-1">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Signals to surface
          </p>
          <div className="flex flex-col">
            {WATCH_CATEGORIES.map((category) => {
              const on = watchCats[category.key];
              return (
                <div
                  key={category.key}
                  className="flex items-center gap-4 border-b border-[var(--divider)] py-3"
                >
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      {category.label}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {category.desc}
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    aria-label={category.label}
                    onClick={() =>
                      setWatchCats((prev) => ({
                        ...prev,
                        [category.key]: !prev[category.key],
                      }))
                    }
                    className={cn(
                      "relative h-6 w-11 flex-none rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      on ? "bg-primary" : "bg-border",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 h-5 w-5 rounded-full bg-card shadow transition-all",
                        on ? "left-[22px]" : "left-0.5",
                      )}
                    />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            How often should Mylo check in?
          </p>
          <div className="flex gap-1 rounded-lg bg-surface-alt p-1">
            {CADENCES.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={cadence === option.id}
                onClick={() => setCadence(option.id)}
                className={cn(
                  "flex-1 rounded-md px-3 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  cadence === option.id
                    ? "bg-primary text-primary-foreground"
                    : "text-[var(--text-secondary)]",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  const panels = [panelAbout, panelImport, panelReview, panelWatch];

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="mb-4 flex items-center gap-4">
        <MyloMark className="h-12 w-11 flex-none" />
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-secondary">
            {editing ? "Edit your research radar" : "Let’s tune your research radar"}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            Step {step + 1} of {STEP_LABELS.length} · {STEP_LABELS[step]}
          </p>
        </div>
      </div>

      <MyceliumBranch
        steps={STEP_LABELS.length}
        current={step}
        className="mb-6 h-10"
      />

      <OnboardingStage current={step} direction={direction} steps={panels} />

      {submitError ? (
        <p
          className="mt-5 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
        >
          {submitError}
        </p>
      ) : null}

      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          onClick={back}
          className="text-sm font-medium text-[var(--text-secondary)] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Back
        </button>
        <Button
          className="rounded-full"
          onClick={primaryAction}
          disabled={importing || reviewBlocked || busy}
        >
          {primaryLabel()}
        </Button>
      </div>

      <p className="mt-4 text-center text-xs text-[var(--text-muted)]">
        You can change any of this later in Settings.
      </p>
    </div>
  );
}
