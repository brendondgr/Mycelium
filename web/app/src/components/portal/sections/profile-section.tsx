"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { usePortal } from "@/components/portal/portal-context";
import { LabSettingsSection } from "@/components/portal/sections/lab-settings-section";
import {
  ProfileEditorModal,
  type ProfileEditorTab,
} from "@/components/portal/sections/profile-editor-modal";
import { Card } from "@/components/portal/primitives/card";
import { clusterAccentVar } from "@/components/portal/primitives/cluster-badge";
import { Pill } from "@/components/portal/primitives/pill";
import { ProgressBar } from "@/components/portal/primitives/progress-bar";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import { CheckIcon } from "@/components/portal/icons";
import {
  useConnectDiscord,
  useDisconnectDiscord,
  useDiscordStatus,
  useIssueActivationCode,
  useProfile,
  useSetDiscordDailyReport,
  useTestDiscordDm,
  useWatch,
} from "@/lib/portal/hooks";
import { computeCompleteness } from "@/lib/portal/completeness";
import type { ClusterGroup, ProfileEligibility } from "@/lib/auth-types";

/** A small colored dot + label used as a cluster group header. */
function ClusterGroupHeading({ cluster }: { cluster: ClusterGroup }) {
  const token = clusterAccentVar(cluster.id);
  return (
    <p
      className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.07em]"
      style={{ color: `var(${token})` }}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: `var(${token})` }}
      />
      {cluster.label}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Research focus card (LEFT)
// ---------------------------------------------------------------------------

function ResearchFocusCard({ onOrganize }: { onOrganize: () => void }) {
  const { data: profile, isLoading, isError } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
          Research focus
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Loading your profile…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
          Research focus
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load your profile.</p>
      </Card>
    );
  }

  const interests = profile?.interests;
  const statement = interests?.statement?.trim() ?? "";
  const keywords = interests?.keywords ?? [];
  const skills = interests?.skills ?? [];

  const hasContent =
    Boolean(statement) || keywords.length > 0 || skills.length > 0;

  return (
    <Card className="p-[22px]">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          Research focus
        </h2>
        <button
          type="button"
          onClick={onOrganize}
          className="text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Organize
        </button>
      </div>

      {/* Statement */}
      {statement ? (
        <p className="mb-4 text-sm leading-relaxed text-[var(--text-secondary)]">
          {statement}
        </p>
      ) : null}

      {/* Keyword / skill chip groups */}
      {[
        { label: "Keywords", items: keywords },
        { label: "Skills", items: skills },
      ]
        .filter(({ items }) => items.length > 0)
        .map(({ label, items }) => (
          <div key={label} className="mb-3">
            <p className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
              {label}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {items.map((item) => (
                <Pill key={item} tone="neutral">
                  {item}
                </Pill>
              ))}
            </div>
          </div>
        ))}

      {!hasContent ? (
        <p className="text-sm text-[var(--text-secondary)]">
          Add a research statement and keywords in your profile so Mylo can match
          work to you.
        </p>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Profile completeness card (RIGHT top)
// ---------------------------------------------------------------------------

function ProfileCompletenessCard() {
  const { data: profile, isLoading, isError } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Profile completeness
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Profile completeness
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load your profile.</p>
      </Card>
    );
  }

  const { percent, items } = computeCompleteness(profile);

  return (
    <Card className="p-[22px]">
      <h2 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
        Profile completeness
      </h2>

      <div className="my-2.5 flex justify-between text-xs font-medium">
        <span className="text-[var(--text-secondary)]">Completeness</span>
        <span className="font-semibold text-[var(--text-secondary)]">{percent}%</span>
      </div>

      <ProgressBar
        value={percent}
        tone="primary"
        label="Profile completeness"
        className="mb-4"
      />

      <div className="flex flex-col gap-2.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2.5 text-sm">
            {item.done ? (
              <CheckIcon
                size={16}
                className="shrink-0 text-primary"
                aria-hidden="true"
              />
            ) : (
              <span
                className="inline-block h-4 w-4 shrink-0 rounded-full border border-[var(--text-muted)]"
                aria-hidden="true"
              />
            )}
            <span
              className={
                item.done
                  ? "text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]"
              }
            >
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// What Mylo watches card (RIGHT bottom)
// ---------------------------------------------------------------------------

function WatchCard({ onEdit }: { onEdit: () => void }) {
  const { data: watch, isLoading, isError } = useWatch();
  const { data: profile } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          What Mylo watches
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          What Mylo watches
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Couldn&apos;t load your watch settings.</p>
      </Card>
    );
  }

  const topics = watch?.topics ?? [];
  const categories = watch?.categories ?? [];
  const cadence = watch?.cadence ?? "weekly";
  const clusters = profile?.interests?.clusters ?? [];

  const cadenceLabel = cadence === "daily" ? "daily" : "weekly";

  // Group watch topics under EVERY cluster (interest-clusters feature): a topic
  // is claimed by the first cluster whose label or one of its areas matches it.
  // Clusters that claim no topic still render — they fall back to showing their
  // own areas — so the card always reflects all of the profile's clusters.
  const claimed = new Set<string>();
  const clusterRows = clusters.map((cluster) => {
    const matched = topics.filter((topic) => {
      if (claimed.has(topic)) return false;
      const key = topic.toLowerCase();
      return (
        cluster.label.toLowerCase() === key ||
        cluster.areas.some((area) => area.toLowerCase() === key)
      );
    });
    matched.forEach((topic) => claimed.add(topic));
    return {
      cluster,
      items: matched.length > 0 ? matched : cluster.areas,
    };
  });
  const otherTopics = topics.filter((topic) => !claimed.has(topic));

  const hasClusters = clusterRows.length > 0;
  const isEmpty = !hasClusters && topics.length === 0;

  return (
    <Card className="p-[22px]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          What Mylo watches
        </h2>
        <button
          type="button"
          onClick={onEdit}
          className="text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Adjust
        </button>
      </div>

      {isEmpty ? (
        <p className="text-sm text-[var(--text-secondary)]">
          You haven&apos;t set watch topics yet.
        </p>
      ) : (
        <>
          {hasClusters ? (
            <div className="mb-3 flex flex-col gap-3">
              {clusterRows.map(({ cluster, items }) => (
                <div key={cluster.id}>
                  <ClusterGroupHeading cluster={cluster} />
                  <div className="flex flex-wrap gap-1.5">
                    {items.map((item) => (
                      <Pill key={item} tone="neutral">
                        {item}
                      </Pill>
                    ))}
                  </div>
                </div>
              ))}
              {otherTopics.length > 0 ? (
                <div>
                  <p className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
                    Other
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {otherTopics.map((topic) => (
                      <Pill key={topic} tone="neutral">
                        {topic}
                      </Pill>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {topics.map((topic) => (
                <Pill key={topic} tone="neutral">
                  {topic}
                </Pill>
              ))}
            </div>
          )}

          {categories.length > 0 ? (
            <p className="mb-1.5 text-xs text-[var(--text-secondary)]">
              Signals:{" "}
              <span className="font-medium">{categories.join(", ")}</span>
            </p>
          ) : null}

          <p className="text-xs text-[var(--text-secondary)]">
            Cadence:{" "}
            <span className="font-medium">{cadenceLabel} digest</span>
          </p>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Eligibility helpers
// ---------------------------------------------------------------------------

const CITIZENSHIP_LABEL: Record<ProfileEligibility["citizenship"], string> = {
  us: "US citizen / permanent resident",
  international: "International student",
};

const STAGE_LABEL: Record<ProfileEligibility["stage"], string> = {
  masters: "Master's",
  doctoral_early: "Early doctoral",
  doctoral_dissertation: "Dissertation research / write-up",
  postdoc: "Postdoc / beyond",
  "": "Not specified",
};

// ---------------------------------------------------------------------------
// Fellowship eligibility card
// ---------------------------------------------------------------------------

function EligibilityCard({ onEdit }: { onEdit: () => void }) {
  const { data: profile, isLoading, isError } = useProfile();

  if (isLoading) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Fellowship eligibility
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">
          Fellowship eligibility
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load your eligibility details.
        </p>
      </Card>
    );
  }

  const eligibility = profile?.interests?.eligibility;

  if (!eligibility) {
    return (
      <Card className="p-[22px]">
        <h2 className="mb-2 text-base font-semibold text-[var(--text-primary)]">
          Fellowship eligibility
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Fellowship matching uses your eligibility profile — citizenship,
          career stage, and field. Set it from{" "}
          <button
            type="button"
            onClick={onEdit}
            className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Edit profile
          </button>
          .
        </p>
      </Card>
    );
  }

  const citizenshipLabel = CITIZENSHIP_LABEL[eligibility.citizenship] ?? eligibility.citizenship;
  const stageLabel = STAGE_LABEL[eligibility.stage] ?? eligibility.stage;
  const fields = eligibility.fields ?? [];
  const restrictions = eligibility.eligible_restrictions ?? [];

  return (
    <Card className="p-[22px]">
      <h2 className="mb-4 text-base font-semibold text-[var(--text-primary)]">
        Fellowship eligibility
      </h2>

      <div className="space-y-3">
        {/* Citizenship */}
        <div className="flex flex-col gap-0.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            Citizenship
          </p>
          <p className="text-sm text-[var(--text-primary)]">{citizenshipLabel}</p>
        </div>

        {/* Stage */}
        <div className="flex flex-col gap-0.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            Career stage
          </p>
          <p className="text-sm text-[var(--text-primary)]">{stageLabel}</p>
        </div>

        {/* Broad fields */}
        <div className="flex flex-col gap-1.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            Broad fields
          </p>
          {fields.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {fields.map((field) => (
                <Pill key={field} tone="primary">
                  {field}
                </Pill>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">None selected</p>
          )}
        </div>

        {/* Restriction groups */}
        <div className="flex flex-col gap-1.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            Eligible restriction groups
          </p>
          {restrictions.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {restrictions.map((r) => (
                <Pill key={r} tone="accent">
                  {r}
                </Pill>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">None selected</p>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Connected services — Discord (RIGHT)
// ---------------------------------------------------------------------------

const DISCORD_RETURN_NOTICE: Record<string, string> = {
  linked: "Discord connected. Mylo can reach you now.",
  installed: "Mylo was added to your server. In the lab's settings, click Activate Lab for a code, then run /activate-lab code:<code> in that server to connect it.",
  conflict: "That Discord account is already linked to another Mycelium user.",
  error: "Something went wrong connecting Discord. Please try again.",
  install_error: "Could not add Mylo to that server. Please try again.",
  login_required: "Please sign in and try connecting Discord again.",
};

function DiscordCard() {
  const { data: status, isLoading } = useDiscordStatus();
  const connect = useConnectDiscord();
  const disconnect = useDisconnectDiscord();
  const issueCode = useIssueActivationCode();
  const testDm = useTestDiscordDm();
  const dailyReport = useSetDiscordDailyReport();
  const searchParams = useSearchParams();
  const notice = DISCORD_RETURN_NOTICE[searchParams.get("discord") ?? ""];

  const connected = Boolean(status?.connected);

  return (
    <Card className="p-[22px]">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          Connected services
        </h2>
        <Pill tone={connected ? "primary" : "neutral"}>
          {connected ? "Discord linked" : "Discord not linked"}
        </Pill>
      </div>

      {notice ? (
        <p className="mb-3 rounded-lg bg-[var(--surface-alt)] px-3 py-2 text-sm text-[var(--text-secondary)]">
          {notice}
        </p>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : connected ? (
        <div className="space-y-3">
          <p className="text-sm text-[var(--text-secondary)]">
            Linked as{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {status?.global_name || status?.username || "your Discord account"}
            </span>
            {status?.link_method === "activation_code" ? " (via code)" : ""}.
          </p>
          <div className="flex items-start justify-between gap-3 rounded-lg bg-[var(--surface-alt)] px-3 py-2.5">
            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Can Mylo reach you?
              </p>
              <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
                {testDm.isError
                  ? "Couldn’t run the test. Try again."
                  : status?.dm_ok === false
                    ? "Mylo can’t DM you — enable “Allow direct messages from server members,” then re-test."
                    : status?.dm_ok
                      ? "Mylo can reach you by direct message."
                      : "Not checked yet — run a test to confirm."}
              </p>
            </div>
            <Button
              variant="secondary"
              className="shrink-0 rounded-full"
              onClick={() => testDm.mutate()}
              disabled={testDm.isPending}
            >
              {testDm.isPending ? "Testing…" : "Test"}
            </Button>
          </div>
          {(() => {
            const reportOn = !status?.daily_report_opt_out;
            return (
              <div className="flex items-start justify-between gap-3 rounded-lg bg-[var(--surface-alt)] px-3 py-2.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    Daily research report
                  </p>
                  <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
                    {dailyReport.isError
                      ? "Couldn’t update. Try again."
                      : reportOn
                        ? "Mylo DMs you a daily PDF of your top papers and opportunities."
                        : "Paused — Mylo won’t DM you the daily report."}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={reportOn}
                  aria-label="Daily research report DM"
                  onClick={() => dailyReport.mutate(reportOn)}
                  disabled={dailyReport.isPending}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${
                    reportOn
                      ? "bg-[var(--primary)]"
                      : "bg-[var(--border)]"
                  }`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                      reportOn ? "translate-x-[22px]" : "translate-x-[2px]"
                    }`}
                  />
                </button>
              </div>
            );
          })()}
          <Button
            variant="secondary"
            className="rounded-full"
            onClick={() => disconnect.mutate()}
            disabled={disconnect.isPending}
          >
            {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-[var(--text-secondary)]">
            Connect Discord so Mylo can reach you and link your lab’s server.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              className="rounded-full"
              onClick={() => connect.mutate()}
              disabled={connect.isPending}
            >
              {connect.isPending ? "Opening Discord…" : "Connect Discord"}
            </Button>
            <Button
              variant="secondary"
              className="rounded-full"
              onClick={() => issueCode.mutate()}
              disabled={issueCode.isPending}
            >
              {issueCode.isPending ? "Generating…" : "Use a code instead"}
            </Button>
          </div>
          {issueCode.data ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-2">
              <p className="text-sm text-[var(--text-secondary)]">
                Run{" "}
                <code className="font-mono text-[var(--text-primary)]">
                  /activate code:{issueCode.data.code}
                </code>{" "}
                in any Discord server Mylo is already in, within{" "}
                {Math.round(issueCode.data.expires_in / 60)} minutes. Shown once.
              </p>
            </div>
          ) : null}
          {issueCode.isError ? (
            <p className="text-sm text-[var(--text-secondary)]">
              Couldn’t generate a code. Try again.
            </p>
          ) : null}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// ProfileSection
// ---------------------------------------------------------------------------

export function ProfileSection() {
  const { currentLab } = usePortal();
  // `null` = closed. Opening carries which tab to land on, so a card's own
  // affordance ("Organize", "Adjust") drops the user straight into that surface
  // instead of the editor's default tab.
  const [editorTab, setEditorTab] = React.useState<ProfileEditorTab | null>(null);

  // In a lab workspace, the Profile slot is the lab's configuration (managers
  // only — the section itself guards non-managers who deep-link here).
  if (currentLab) {
    return <LabSettingsSection lab={currentLab} />;
  }

  return (
    <div>
      <SectionHeader
        eyebrow="Workspace"
        title="Profile"
        subtitle="Your research focus and goals — what Mylo uses to find matches."
        action={
          <Button className="rounded-full" onClick={() => setEditorTab("focus")}>
            Edit profile
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-[1.3fr_1fr] lg:items-start">
        {/* LEFT — research focus + connected services + fellowship eligibility */}
        <div className="flex flex-col gap-[22px]">
          <ResearchFocusCard onOrganize={() => setEditorTab("interests")} />
          <DiscordCard />
          <EligibilityCard onEdit={() => setEditorTab("eligibility")} />
        </div>

        {/* RIGHT — what Mylo watches + completeness. Plans and anything else
            monetary live on their own Billing page, not in the open here. */}
        <div className="flex flex-col gap-[22px]">
          <WatchCard onEdit={() => setEditorTab("watch")} />
          <ProfileCompletenessCard />
        </div>
      </div>

      {editorTab ? (
        <ProfileEditorModal
          open
          initialTab={editorTab}
          onClose={() => setEditorTab(null)}
        />
      ) : null}
    </div>
  );
}
