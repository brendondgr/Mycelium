"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { MyloMark } from "@/components/brand/mylo-mark";
import {
  ClusterOrganizer,
  clampClustersToCaps,
} from "@/components/onboarding/cluster-organizer";
import MyceliumBranch from "@/components/onboarding/mycelium-branch";
import { OnboardingMatch } from "@/components/onboarding/onboarding-match";
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
  proposeClusters,
  saveProfileBasics,
  saveWatch,
  resendVerificationCode,
  synthesizeProfile,
  verifyEmailCode,
} from "@/lib/auth-client";
import { fetchProfile } from "@/lib/portal/client";
import { useEntitlements } from "@/lib/portal/hooks";
import type {
  ClusterGroup,
  OnboardingMatchArea,
  ProfileEligibility,
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
  { key: "conferences", label: "Conferences & CFPs", desc: "Meetings and calls for papers in your field." },
  { key: "collaborators", label: "Potential collaborators", desc: "People on adjacent problems." },
  { key: "retractions", label: "Retractions & corrections", desc: "When work you cited changes." },
  { key: "graph", label: "Knowledge-graph updates", desc: "New connections across your network." },
];

const CADENCES: { id: WatchCadence; label: string }[] = [
  { id: "daily", label: "Daily digest" },
  { id: "weekly", label: "Weekly digest" },
];

/**
 * The onboarding steps, in order. The watch step comes *before* fellowship
 * eligibility, and eligibility only appears when the user keeps the Fellowships
 * signal on — so the eligibility questions are only asked of people who actually
 * want fellowship recommendations.
 */
type StepKey =
  | "about"
  | "import"
  | "review"
  | "organize"
  | "watch"
  | "eligibility";

const STEP_LABEL: Record<StepKey, string> = {
  about: "About you",
  import: "Import your research",
  review: "Review profile",
  organize: "Organize interests",
  watch: "What Mylo watches",
  eligibility: "Fellowship eligibility",
};

/** Steps every onboarding shows, in order; eligibility is appended when opted in. */
const BASE_STEP_KEYS: StepKey[] = [
  "about",
  "import",
  "review",
  "organize",
  "watch",
];

/**
 * The opportunity areas the live post-onboarding match can run, in report order.
 * Each maps to a watch-category key, so a user only matches the areas they kept on.
 */
const MATCH_AREA_ORDER: OnboardingMatchArea[] = [
  "papers",
  "grants",
  "fellowships",
  "conferences",
];

/** Fellowship eligibility constants */
const CITIZENSHIP_OPTIONS: { value: ProfileEligibility["citizenship"]; label: string }[] = [
  { value: "us", label: "US citizen / permanent resident" },
  { value: "international", label: "International student" },
];

// No "Not applicable" option: an unset stage is not a preference, it is a gap —
// the fellowship matcher stops filtering on stage entirely for anyone it cannot
// place, which is how postdoctoral awards reached doctoral students. "Postdoc /
// beyond" is the catch-all for everyone past the doctorate.
const STAGE_OPTIONS: {
  value: Exclude<ProfileEligibility["stage"], "">;
  label: string;
}[] = [
  { value: "masters", label: "Master's" },
  { value: "doctoral_early", label: "Early doctoral" },
  { value: "doctoral_dissertation", label: "Dissertation research / write-up" },
  { value: "postdoc", label: "Postdoc / beyond" },
];

const FIELD_OPTIONS = [
  "Social Sciences",
  "Sciences/Engineering/Math",
  "Professional Programs",
  "Fine Arts",
  "Humanities",
];

const RESTRICTION_OPTIONS = ["Women", "Equity"];

const MAX_RESUME_BYTES = 5 * 1024 * 1024;

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

  // Tier caps drive the interactive limits in the organizer and the watch step,
  // so a user is told their plan's limits up front instead of discovering them
  // through a rejected save. Falls back to the Free plan (3 clusters × 2 topics =
  // 6) until the entitlements load, so a brand-new account is never briefly
  // shown a laxer limit than it actually has.
  const { data: entitlements } = useEntitlements();
  const clusterCap = entitlements?.cluster_cap ?? 3;
  const clusterTopicCap = entitlements?.cluster_topic_cap ?? 2;
  const topicCap = entitlements?.topic_cap ?? 6;
  const [screen, setScreen] = useState<
    "verify" | "intake" | "synthesizing" | "building" | "matching"
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

  // Step 3 — organize interests into clusters
  const [clusters, setClusters] = useState<ClusterGroup[]>([]);
  // Guards the one-time auto-propose call on first landing on the organize
  // step — never retried automatically after that (the ClusterOrganizer's own
  // "Organize with Mylo" button covers a failed or skipped attempt).
  const autoProposedRef = useRef(false);

  // Step 4 — fellowship eligibility
  const [eligCitizenship, setEligCitizenship] = useState<ProfileEligibility["citizenship"]>("us");
  const [eligStage, setEligStage] = useState<ProfileEligibility["stage"]>("");
  const [eligFields, setEligFields] = useState<string[]>([]);
  const [eligRestrictions, setEligRestrictions] = useState<string[]>([]);
  // Opt-in: share fellowship eligibility with the user's labs (default off).
  const [eligLabVisible, setEligLabVisible] = useState(false);
  // Preserve any pre-existing career_stage (set by other code paths, not this step).
  const [eligCareerStage, setEligCareerStage] = useState<string | undefined>(undefined);
  // Year the doctorate was conferred, as typed. Kept a string so the field can be
  // empty; parsed once on save.
  const [eligPhdYear, setEligPhdYear] = useState("");

  // Step 4 — watch
  const [watchTopics, setWatchTopics] = useState<string[]>([]);
  const [watchCats, setWatchCats] = useState<Record<string, boolean>>({
    papers: true,
    grants: true,
    fellowships: true,
    conferences: true,
    collaborators: false,
    retractions: false,
    graph: true,
  });
  const [cadence, setCadence] = useState<WatchCadence>("weekly");

  // Areas the live post-onboarding match will run, set from the watch toggles
  // when the user finishes (first-run only).
  const [matchAreas, setMatchAreas] = useState<OnboardingMatchArea[]>([]);

  // Verify (scaffold)
  const [code, setCode] = useState<string[]>(["", "", "", "", "", ""]);
  const [verifyError, setVerifyError] = useState("");
  const [verifyResent, setVerifyResent] = useState(false);
  const codeRefs = useRef<Array<HTMLInputElement | null>>([]);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sourceOption = SOURCES.find((option) => option.value === source) ?? null;
  const hasImportInput = Boolean((source && identifier.trim()) || resumeFile);

  // The live step list: the fellowship-eligibility step is only present when the
  // user keeps the Fellowships signal on. Toggling it happens on the watch step
  // (index 3), which sits before eligibility, so the current index stays valid.
  const stepKeys: StepKey[] = watchCats.fellowships
    ? [...BASE_STEP_KEYS, "eligibility"]
    : BASE_STEP_KEYS;
  const lastStep = stepKeys.length - 1;
  const currentKey = stepKeys[Math.min(step, lastStep)];

  function goStep(target: number, dir: number) {
    setDirection(dir);
    setStep(target);
    window.scrollTo(0, 0);
  }

  /**
   * Derive a sensible default career stage from a role value.
   * Used to pre-select in the eligibility step when the user is not in edit
   * mode (edit mode loads from the saved profile instead).
   *
   * Mirrors `TITLE_TO_STAGE` on the backend, including its refusals: a
   * "Researcher" or "Staff Scientist" could be at any point on the ladder, so
   * neither pre-fills anything and the step asks. A PI maps to the top rung,
   * which — the stage gate being asymmetric — can only ever widen their feed.
   */
  function stageFromRole(roleValue: string): ProfileEligibility["stage"] {
    if (roleValue === "postdoc" || roleValue === "pi") return "postdoc";
    if (roleValue === "student") return "doctoral_early";
    return "";
  }

  function applyInterests(interests: ResearchInterests) {
    setStatement(interests.statement ?? "");
    setAreas(interests.areas ?? []);
    setKeywords(interests.keywords ?? []);
    setSkills(interests.skills ?? []);
    setDraftSources(interests.sources ?? {});
    // Mylo now builds theme clusters during synthesis — carry them into the
    // organize step (clamped to the plan) so it opens pre-grouped instead of
    // empty; this also short-circuits the step's one-time auto-propose.
    if (interests.clusters?.length) {
      setClusters(
        clampClustersToCaps(interests.clusters, {
          maxClusters: clusterCap,
          maxTopicsPerCluster: clusterTopicCap,
        }),
      );
    }
    const seed = dedupe([
      ...(interests.areas ?? []),
      ...(interests.keywords ?? []),
    ]).slice(0, topicCap);
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
          // Load saved clusters as-is — a plan downgrade never destroys a user's
          // existing grouping (the organizer still blocks *new* over-cap edits,
          // and the save truncates to the current cap). Clamping here would use
          // the still-loading Free fallback and wrongly shrink a paid user's data.
          setClusters(interests.clusters ?? []);
          if (interests.eligibility) {
            const elig = interests.eligibility;
            setEligCitizenship(elig.citizenship ?? "us");
            setEligStage(elig.stage ?? "");
            setEligFields(elig.fields ?? []);
            setEligRestrictions(elig.eligible_restrictions ?? []);
            setEligLabVisible(elig.lab_visible ?? false);
            setEligCareerStage(elig.career_stage);
            setEligPhdYear(
              elig.phd_completed_year ? String(elig.phd_completed_year) : "",
            );
          }
        }
        if (watch) {
          // As-is on load (see clusters above); the save truncates to the cap.
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

  // -- organize (auto-propose) ---------------------------------------------
  // The first time the user reaches the organize step with no clusters yet
  // and enough areas to group, ask Mylo for a starting grouping so the step
  // never opens empty. Runs at most once per flow — a failed or skipped
  // attempt is never retried automatically; the ClusterOrganizer's own
  // "Organize with Mylo" button covers that.
  useEffect(() => {
    if (currentKey !== "organize" || autoProposedRef.current) {
      return;
    }
    if (clusters.length > 0) {
      autoProposedRef.current = true;
      return;
    }
    if (areas.length < 2) {
      // A single area is one implicit cluster — nothing to propose.
      return;
    }
    autoProposedRef.current = true;
    (async () => {
      try {
        const result = await proposeClusters({ areas, keywords, statement });
        setClusters(
          clampClustersToCaps(result.clusters, {
            maxClusters: clusterCap,
            maxTopicsPerCluster: clusterTopicCap,
          }),
        );
        if (result.watch_topics.length) {
          setWatchTopics(result.watch_topics.slice(0, topicCap));
        }
      } catch {
        // Degrade silently — the manual "Organize with Mylo" button covers this.
      }
    })();
  }, [
    currentKey,
    clusters.length,
    areas,
    keywords,
    statement,
    clusterCap,
    clusterTopicCap,
    topicCap,
  ]);

  // -- verify --------------------------------------------------------------

  /**
   * Submit the code that was mailed at sign-up.
   *
   * A wrong code stops here rather than waving the person through: verifying is
   * what activates the account, and an account that silently believed itself
   * verified would hit a 403 the first time it tried to build a lab. Skipping is
   * still allowed — it just leaves the account unactivated, which the Account
   * page says plainly.
   */
  async function verifyAndContinue() {
    if (code.some((digit) => digit === "")) {
      setVerifyError("Enter all 6 digits, or skip for now.");
      return;
    }
    setVerifyError("");
    setBusy(true);
    try {
      await verifyEmailCode(code.join(""));
    } catch (error) {
      setVerifyError(
        error instanceof Error
          ? error.message
          : "That code is not valid. Ask for a new one.",
      );
      setBusy(false);
      return;
    }
    setBusy(false);
    enterIntake();
  }

  /** Mail a fresh code, replacing whatever was outstanding. */
  async function resendCode() {
    setVerifyError("");
    try {
      await resendVerificationCode();
      setVerifyResent(true);
    } catch (error) {
      setVerifyError(
        error instanceof Error
          ? error.message
          : "Could not send a new code. Try again in a moment.",
      );
    }
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
  const reviewBlocked = currentKey === "review" && areas.length < 1;
  // Stage is what makes fellowship eligibility mean anything: without it the
  // matcher cannot tell a postdoctoral award from a doctoral one and stops
  // filtering on stage entirely. Most people never see this block — the role
  // they picked two steps ago pre-fills it — so requiring an answer costs a
  // click only for the roles that genuinely do not imply a stage.
  const stageMissing = currentKey === "eligibility" && !eligStage;

  function primaryAction() {
    if (currentKey === "import") {
      void runImport();
      return;
    }
    if (currentKey === "review" && areas.length < 1) {
      return;
    }
    if (stageMissing) {
      return;
    }
    if (step < lastStep) {
      goStep(step + 1, 1);
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
    if (currentKey === "import") {
      return importing ? "Growing…" : hasImportInput ? "Grow my profile" : "Continue";
    }
    if (step === lastStep) {
      if (editing) {
        return busy ? "Saving…" : "Save changes";
      }
      return "Find my matches";
    }
    return "Continue";
  }

  async function finish() {
    setSubmitError(null);
    const interests: ResearchInterests = { version: 2, areas };
    // The interests contract requires that IF `clusters` is present, every area
    // is in exactly one cluster (no orphan, no phantom, no duplicate). Sanitize
    // against the *current* areas first (the user may have edited areas after
    // organizing), then attach only when the sanitized clusters cover every area
    // — otherwise omit the key entirely, a valid v1-shaped fallback. This never
    // sends a partial partition, so the save can't 400 on the partition rule.
    const validAreas = new Set(areas);
    const claimed = new Set<string>();
    const cleaned = clusters
      .map((cluster) => ({
        ...cluster,
        areas: cluster.areas.filter((area) => {
          if (!validAreas.has(area) || claimed.has(area)) return false;
          claimed.add(area);
          return true;
        }),
      }))
      .filter((cluster) => cluster.areas.length > 0);
    if (cleaned.length > 0 && areas.every((area) => claimed.has(area))) {
      interests.clusters = cleaned;
    }
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
    // Always attach the eligibility block (defaults are safe); preserve any
    // existing career_stage that was loaded from the profile in edit mode.
    const eligibility: ProfileEligibility = {
      citizenship: eligCitizenship,
      stage: eligStage,
      fields: eligFields,
      eligible_restrictions: eligRestrictions,
      lab_visible: eligLabVisible,
    };
    if (eligCareerStage !== undefined) {
      eligibility.career_stage = eligCareerStage;
    }
    // Only ever sent for a postdoc, and only when it parses — the backend gates
    // on the award's post-doctorate window solely when both sides are known, so a
    // junk year would be worse than none.
    const phdYear = Number.parseInt(eligPhdYear, 10);
    if (
      eligStage === "postdoc" &&
      Number.isFinite(phdYear) &&
      phdYear >= 1900 &&
      phdYear <= 2200
    ) {
      eligibility.phd_completed_year = phdYear;
    }
    interests.eligibility = eligibility;

    const categories = WATCH_CATEGORIES.filter((c) => watchCats[c.key]).map(
      (c) => c.key,
    );

    // Final backstop so the watch save can never be rejected for exceeding the
    // plan: keep only the first `topicCap` topics. The organizer already holds
    // the user at/under this, so in practice this trims nothing — it just makes
    // an over-cap edge (e.g. a downgrade) save cleanly instead of erroring out.
    const cappedTopics = watchTopics.slice(0, topicCap);

    const saves = (): Promise<unknown>[] => [
      saveProfileBasics({
        academic_title: role,
        ...(institution.trim() ? { institution: institution.trim() } : {}),
      }),
      confirmInterests(interests),
      saveWatch({ topics: cappedTopics, categories, cadence }),
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

    // First-run: save the profile, then hand off to the live match window (which
    // matches the just-saved interests and, when done, enters the workspace)
    // instead of jumping straight to the overview.
    setScreen("building");
    try {
      await Promise.all([...saves(), wait(1200)]);
      setMatchAreas(MATCH_AREA_ORDER.filter((area) => watchCats[area]));
      setScreen("matching");
    } catch (error) {
      setScreen("intake");
      setStep(lastStep);
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
        <MyloMark className="mylo-float h-14 w-14" />
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
          <div className="absolute left-1/2 top-[55%] h-[82px] w-[82px] -translate-x-1/2 -translate-y-1/2">
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

  // -- matching (live post-onboarding match) -------------------------------
  if (screen === "matching") {
    return (
      <OnboardingMatch
        areas={matchAreas}
        onDone={() => {
          router.replace("/app/overview");
          router.refresh();
        }}
      />
    );
  }

  // -- verify --------------------------------------------------------------
  if (screen === "verify") {
    return (
      <div className="mx-auto w-full max-w-md text-center">
        <MyloMark className="mylo-float mx-auto mb-4 h-16 w-16" />
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
                onClick={() => void resendCode()}
              >
                Resend code
              </button>
            </span>
          )}
        </div>

        <div className="mt-5 flex items-center justify-center gap-4 border-t border-[var(--divider)] pt-4 text-sm">
          <button
            type="button"
            className="text-[var(--text-muted)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={enterIntake}
          >
            Skip for now
          </button>
        </div>
        <p className="mt-4 text-xs text-[var(--text-muted)]">
          You&rsquo;re signed in either way. Verifying activates your account —
          until then you can&rsquo;t create a lab or department, or invite
          anyone. You can finish it later from your Account page.
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
                onClick={() => {
                  setRole(option.value);
                  // In new onboarding, seed a sensible default stage so the
                  // eligibility step feels pre-filled. Edit mode loads the
                  // saved profile value instead, so we skip the override there.
                  if (!editing) {
                    setEligStage(stageFromRole(option.value));
                  }
                }}
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

  const panelOrganize = (
    <div className={cardClass}>
      <div className="space-y-5">
        <div>
          <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            Shape your research clusters
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Group related areas together so Mylo can report on each thread of
            your work separately. Optional — skip it and everything stays in
            one group.
          </p>
        </div>
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
      </div>
    </div>
  );

  const panelEligibility = (
    <div className={cardClass}>
      <div className="space-y-5">
        <div>
          <h2 className="font-serif text-2xl font-semibold text-[var(--text-primary)]">
            Fellowship eligibility
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Fellowships are matched by eligibility, not just topics. These
            answers let Mylo filter to opportunities you can actually apply for.
            Career stage is the one we need — without it, awards written for a
            later stage keep showing up. The rest can be skipped; you can update
            any of it later.
          </p>
        </div>

        {/* Citizenship */}
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
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

        {/* Career stage — the one required answer on this step. */}
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Career stage <span className="text-[var(--clay)]">*</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {STAGE_OPTIONS.map((option) => (
              <Chip
                key={option.value}
                selected={eligStage === option.value}
                onClick={() => setEligStage(option.value)}
              >
                {option.label}
              </Chip>
            ))}
          </div>
          {!eligStage ? (
            <p className="text-xs text-[var(--text-muted)]">
              Pick the one closest to where you are — it decides which awards are
              even open to you.
            </p>
          ) : null}
        </div>

        {/* Years since the doctorate — only postdocs are ever asked. */}
        {eligStage === "postdoc" ? (
          <div className="space-y-2">
            <label
              htmlFor="phd-year"
              className="block text-sm font-medium text-[var(--text-primary)]"
            >
              Year your PhD was conferred{" "}
              <span className="text-[var(--text-muted)]">(optional)</span>
            </label>
            <input
              id="phd-year"
              type="number"
              inputMode="numeric"
              min={1900}
              max={2200}
              value={eligPhdYear}
              onChange={(event) => setEligPhdYear(event.target.value)}
              placeholder="e.g. 2024"
              className="w-40 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <p className="text-xs text-[var(--text-muted)]">
              Many early-career awards close a fixed number of years after the
              doctorate. Without this, Mylo cannot apply those limits.
            </p>
          </div>
        ) : null}

        {/* Broad fields */}
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
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
                      ? prev.filter((f) => f !== field)
                      : [...prev, field],
                  )
                }
              >
                {field}
              </Chip>
            ))}
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Used to match fellowships to your discipline — leave empty if
            you&rsquo;re not sure.
          </p>
        </div>

        {/* Restriction groups */}
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Eligible restriction groups{" "}
            <span className="text-[var(--text-muted)]">(optional)</span>
          </p>
          <div className="flex flex-col gap-2">
            {RESTRICTION_OPTIONS.map((group) => {
              const checked = eligRestrictions.includes(group);
              return (
                <label
                  key={group}
                  className="flex cursor-pointer items-center gap-3"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      setEligRestrictions((prev) =>
                        prev.includes(group)
                          ? prev.filter((r) => r !== group)
                          : [...prev, group],
                      )
                    }
                    className="h-4 w-4 rounded border border-border bg-card accent-primary focus-visible:ring-2 focus-visible:ring-ring"
                  />
                  <span className="text-sm font-medium text-[var(--text-primary)]">
                    {group}
                  </span>
                </label>
              );
            })}
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Some fellowships are restricted to specific groups. Select any that
            apply to you — this is optional and only used to surface more
            relevant opportunities.
          </p>
        </div>

        {/* Lab-visible eligibility consent (opt-in, default off) */}
        <div className="space-y-2">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Share eligibility with my labs{" "}
            <span className="text-[var(--text-muted)]">(optional)</span>
          </p>
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={eligLabVisible}
              onChange={() => setEligLabVisible((v) => !v)}
              className="mt-0.5 h-4 w-4 rounded border border-border bg-card accent-primary focus-visible:ring-2 focus-visible:ring-ring"
            />
            <span className="text-sm font-medium text-[var(--text-primary)]">
              Let my labs see which fellowships I&rsquo;m eligible for
            </span>
          </label>
          <p className="text-xs text-[var(--text-muted)]">
            Off by default. When on, a lab you belong to can see fellowships you
            personally qualify for (so a PI can suggest applying). Your labs are
            never shown fellowships you&rsquo;re <em>not</em> eligible for, so this
            can&rsquo;t reveal your citizenship or career stage.
          </p>
        </div>
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
          maxItems={topicCap}
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

  const panelByKey: Record<StepKey, ReactNode> = {
    about: panelAbout,
    import: panelImport,
    review: panelReview,
    organize: panelOrganize,
    watch: panelWatch,
    eligibility: panelEligibility,
  };
  const panels = stepKeys.map((key) => panelByKey[key]);

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="mb-4 flex items-center gap-4">
        <MyloMark className="h-12 w-12 flex-none" />
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-secondary">
            {editing ? "Edit your research radar" : "Let’s tune your research radar"}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            Step {Math.min(step, lastStep) + 1} of {stepKeys.length} ·{" "}
            {STEP_LABEL[currentKey]}
          </p>
        </div>
      </div>

      <MyceliumBranch
        steps={stepKeys.length}
        current={Math.min(step, lastStep)}
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
          disabled={importing || reviewBlocked || stageMissing || busy}
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
