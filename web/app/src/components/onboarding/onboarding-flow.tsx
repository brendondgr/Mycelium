"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { MyloMark } from "@/components/brand/mylo-mark";
import { saveOnboarding, verifyEmail } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

const inputClass =
  "min-h-11 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60";

const ROLES = [
  { label: "Student", value: "student" },
  { label: "Postdoc", value: "postdoc" },
  { label: "Researcher", value: "researcher" },
  { label: "Principal Investigator", value: "pi" },
  { label: "Staff Scientist", value: "staff" },
];

const AREAS = [
  "Genomics",
  "Neuroscience",
  "Microbial Ecology",
  "Machine Learning",
  "Climate Science",
  "Materials",
  "Public Health",
  "Bioinformatics",
  "Immunology",
  "Synthetic Biology",
  "Ecology",
  "Chemistry",
];

// Step 2 / 4 collect preferences with no backend home yet — captured for the UX
// but intentionally not persisted this sprint (see plan A3).
const GOALS = [
  { id: "track", label: "Track a fast-moving field", desc: "Daily watch on new papers & preprints." },
  { id: "proposal", label: "Build a grant or proposal", desc: "Gather evidence and map claims." },
  { id: "review", label: "Run a literature review", desc: "Synthesize a body of work fast." },
  { id: "collaborators", label: "Find collaborators", desc: "Surface people on adjacent problems." },
  { id: "funding", label: "Monitor fellowships & funding", desc: "Get matched opportunities on time." },
  { id: "strengthen", label: "Strengthen a current paper", desc: "Find support and counter-evidence." },
];

const WATCH = [
  { key: "papers", label: "New papers & preprints", desc: "Relevant to your areas and goals." },
  { key: "grants", label: "Grant deadlines", desc: "Funding that fits your profile." },
  { key: "fellowships", label: "Fellowships", desc: "Matched to your stage and timeline." },
  { key: "retractions", label: "Retractions & corrections", desc: "When work you cited changes." },
  { key: "collaborators", label: "Potential collaborators", desc: "People on adjacent problems." },
  { key: "graph", label: "Knowledge-graph updates", desc: "New connections across your network." },
];

const CADENCES = [
  { id: "daily", label: "Daily digest" },
  { id: "weekly", label: "Weekly digest" },
  { id: "realtime", label: "Real-time" },
];

const KEYWORD_SUGGESTIONS = [
  "CRISPR",
  "meta-analysis",
  "Bayesian models",
  "field sampling",
  "scRNA-seq",
  "remote sensing",
];

const STEP_LABELS = [
  "Your profile",
  "Research areas",
  "Your goals",
  "Research focus",
  "Alerts & cadence",
];

const DEMO_CODE = ["4", "8", "2", "9", "1", "3"];

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function Chip({
  selected,
  disabled,
  onClick,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-full border px-4 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-card text-[var(--text-secondary)] hover:border-brand-secondary",
      )}
    >
      {children}
    </button>
  );
}

type OnboardingFlowProps = {
  email: string;
};

export function OnboardingFlow({ email }: OnboardingFlowProps) {
  const router = useRouter();
  const [screen, setScreen] = useState<"verify" | "intake" | "building">(
    "verify",
  );
  const [step, setStep] = useState(0);

  const [role, setRole] = useState("researcher");
  const [institution, setInstitution] = useState("");
  const [areas, setAreas] = useState<string[]>([]);
  const [goals, setGoals] = useState<string[]>([]);
  const [focusText, setFocusText] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordDraft, setKeywordDraft] = useState("");
  const [watch, setWatch] = useState<Record<string, boolean>>({
    papers: true,
    grants: true,
    fellowships: true,
    retractions: false,
    collaborators: false,
    graph: true,
  });
  const [cadence, setCadence] = useState("weekly");

  const [code, setCode] = useState<string[]>(["", "", "", "", "", ""]);
  const [verifyError, setVerifyError] = useState("");
  const [verifyResent, setVerifyResent] = useState(false);
  const codeRefs = useRef<Array<HTMLInputElement | null>>([]);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle(list: string[], value: string): string[] {
    return list.includes(value)
      ? list.filter((v) => v !== value)
      : [...list, value];
  }

  function addKeyword(raw?: string) {
    const value = (raw ?? keywordDraft).trim();
    if (!value) {
      return;
    }
    setKeywords((prev) =>
      prev.some((k) => k.toLowerCase() === value.toLowerCase())
        ? prev
        : [...prev, value],
    );
    setKeywordDraft("");
  }

  // -- verify --------------------------------------------------------------
  async function verifyAndContinue() {
    if (code.some((d) => d === "")) {
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
    window.scrollTo(0, 0);
  }

  // -- intake nav ----------------------------------------------------------
  const intakeBlocked = step === 1 && areas.length < 1;

  function next() {
    if (intakeBlocked) {
      return;
    }
    if (step < 4) {
      setStep(step + 1);
      window.scrollTo(0, 0);
      return;
    }
    void finish();
  }

  function back() {
    if (step > 0) {
      setStep(step - 1);
      window.scrollTo(0, 0);
    } else {
      setScreen("verify");
    }
  }

  async function finish() {
    setSubmitError(null);
    const interests: {
      version: number;
      areas: string[];
      statement?: string;
      keywords?: string[];
    } = { version: 1, areas };
    if (focusText.trim()) {
      interests.statement = focusText.trim();
    }
    if (keywords.length) {
      interests.keywords = keywords;
    }

    setScreen("building");
    try {
      await Promise.all([
        saveOnboarding({
          academic_title: role,
          ...(institution.trim() ? { institution: institution.trim() } : {}),
          interests,
        }),
        wait(1400),
      ]);
      router.replace("/app");
      router.refresh();
    } catch (error) {
      setScreen("intake");
      setStep(4);
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Could not save your answers. Try again.",
      );
    }
  }

  if (screen === "building") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <MyloMark className="h-20 w-[72px] motion-safe:animate-pulse" />
        <h2 className="text-2xl font-semibold text-[var(--text-primary)]">
          Weaving your knowledge graph…
        </h2>
        <p className="max-w-sm text-[var(--text-secondary)]">
          Seeding {areas[0] ?? "your interests"} and queuing your first scan.
        </p>
      </div>
    );
  }

  if (screen === "verify") {
    return (
      <div className="mx-auto w-full max-w-md text-center">
        <MyloMark className="mx-auto mb-4 h-16 w-[58px]" />
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">
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
                const v = event.target.value.replace(/\D/g, "").slice(-1);
                setCode((prev) => {
                  const nextCode = [...prev];
                  nextCode[index] = v;
                  return nextCode;
                });
                setVerifyError("");
                if (v && index < 5) {
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
              className="h-14 w-12 rounded-md border border-input bg-card text-center text-xl font-semibold text-foreground shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring"
            />
          ))}
        </div>

        {verifyError ? (
          <p className="mt-3 text-sm text-destructive" role="alert">
            {verifyError}
          </p>
        ) : null}

        <Button
          className="mx-auto mt-6 w-full max-w-xs"
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

  // -- intake --------------------------------------------------------------
  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="mb-4 flex items-center gap-4">
        <MyloMark className="h-12 w-11 flex-none" />
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-secondary">
            Let&rsquo;s tune your research radar
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            Step {step + 1} of 5 · {STEP_LABELS[step]}
          </p>
        </div>
      </div>
      <div className="mb-6 h-1.5 overflow-hidden rounded-full bg-surface-alt">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${((step + 1) / 5) * 100}%` }}
        />
      </div>

      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
        {submitError ? (
          <p
            className="mb-5 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {submitError}
          </p>
        ) : null}

        {step === 0 ? (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                First, tell us about you
              </h2>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                This calibrates how Mylo weights papers, methods, and
                opportunities.
              </p>
            </div>
            <div className="space-y-3">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Your role
              </p>
              <div className="flex flex-wrap gap-2">
                {ROLES.map((r) => (
                  <Chip
                    key={r.value}
                    selected={role === r.value}
                    onClick={() => setRole(r.value)}
                  >
                    {r.label}
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
        ) : null}

        {step === 1 ? (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                What are you exploring?
              </h2>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Pick the areas closest to your work — Mylo seeds your knowledge
                graph from these.{" "}
                {areas.length ? (
                  <span className="text-[var(--text-muted)]">
                    ({areas.length} selected)
                  </span>
                ) : null}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {AREAS.map((area) => (
                <Chip
                  key={area}
                  selected={areas.includes(area)}
                  onClick={() => setAreas((prev) => toggle(prev, area))}
                >
                  {area}
                </Chip>
              ))}
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                What do you want Mycelium to help with?
              </h2>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Pick all that apply — Mylo prioritizes these across your
                dashboard.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {GOALS.map((g) => {
                const selected = goals.includes(g.id);
                return (
                  <button
                    key={g.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setGoals((prev) => toggle(prev, g.id))}
                    className={cn(
                      "rounded-lg border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      selected
                        ? "border-primary bg-secondary"
                        : "border-border bg-card hover:border-brand-secondary",
                    )}
                  >
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      {g.label}
                    </span>
                    <span className="mt-1 block text-xs text-[var(--text-muted)]">
                      {g.desc}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                Tell us about your current research
              </h2>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                A sentence or two helps Mylo find the right papers and people.
                You can refine this anytime.
              </p>
            </div>
            <textarea
              value={focusText}
              onChange={(event) => setFocusText(event.target.value)}
              placeholder="e.g. We study how soil microbial communities respond to drought, using metagenomics and multi-year field sampling."
              className={cn(inputClass, "min-h-28 py-3 leading-relaxed")}
            />
            <div className="space-y-2">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Keywords &amp; methods
              </p>
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-input bg-card p-2">
                {keywords.map((k) => (
                  <span
                    key={k}
                    className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground"
                  >
                    {k}
                    <button
                      type="button"
                      aria-label={`Remove ${k}`}
                      onClick={() =>
                        setKeywords((prev) => prev.filter((x) => x !== k))
                      }
                      className="text-[var(--text-muted)] hover:text-foreground"
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  value={keywordDraft}
                  onChange={(event) => setKeywordDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addKeyword();
                    }
                  }}
                  placeholder="Type a keyword and press Enter"
                  className="min-w-40 flex-1 bg-transparent px-1 py-1 text-sm text-foreground outline-none"
                />
              </div>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-xs text-[var(--text-muted)]">Try:</span>
                {KEYWORD_SUGGESTIONS.filter(
                  (s) =>
                    !keywords.some((k) => k.toLowerCase() === s.toLowerCase()),
                )
                  .slice(0, 5)
                  .map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => addKeyword(s)}
                      className="rounded-full border border-dashed border-border px-3 py-1 text-xs font-medium text-[var(--text-secondary)] transition hover:border-brand-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      + {s}
                    </button>
                  ))}
              </div>
            </div>
          </div>
        ) : null}

        {step === 4 ? (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold text-[var(--text-primary)]">
                What should Mylo keep an eye on?
              </h2>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Toggle the signals you care about. Mylo only alerts when
                something clears your relevance bar.
              </p>
            </div>
            <div className="flex flex-col">
              {WATCH.map((w) => {
                const on = watch[w.key];
                return (
                  <div
                    key={w.key}
                    className="flex items-center gap-4 border-b border-[var(--divider)] py-3"
                  >
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {w.label}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {w.desc}
                      </p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={on}
                      aria-label={w.label}
                      onClick={() =>
                        setWatch((prev) => ({ ...prev, [w.key]: !prev[w.key] }))
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
            <div className="space-y-2">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                How often should Mylo check in?
              </p>
              <div className="flex gap-1 rounded-lg bg-surface-alt p-1">
                {CADENCES.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={cadence === c.id}
                    onClick={() => setCadence(c.id)}
                    className={cn(
                      "flex-1 rounded-md px-3 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      cadence === c.id
                        ? "bg-primary text-primary-foreground"
                        : "text-[var(--text-secondary)]",
                    )}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-7 flex items-center justify-between border-t border-[var(--divider)] pt-5">
          <button
            type="button"
            onClick={back}
            className="text-sm font-medium text-[var(--text-secondary)] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Back
          </button>
          <Button onClick={next} disabled={intakeBlocked}>
            {step < 4 ? "Continue" : "Enter Mycelium"}
          </Button>
        </div>
      </div>
      <p className="mt-4 text-center text-xs text-[var(--text-muted)]">
        You can change any of this later in Settings.
      </p>
    </div>
  );
}
