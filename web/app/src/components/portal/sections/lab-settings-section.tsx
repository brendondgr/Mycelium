"use client";

import * as React from "react";

import { AnnouncementsCard } from "@/components/portal/sections/announcements-card";
import { AgentPolicyCard } from "@/components/portal/mylo/settings-cards";
import { DiscordHealthCard } from "@/components/portal/sections/discord-health-card";
import { CloseIcon, EditIcon, TargetIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { EmptyState } from "@/components/portal/primitives/empty-state";
import { SectionHeader } from "@/components/portal/primitives/section-header";
import {
  LabEditorModal,
  type LabEditorTab,
} from "@/components/portal/sections/lab-editor-modal";
import {
  DiscordSyncCard,
  LabPurposeCard,
  MembersCard,
  ProjectsCard,
} from "@/components/portal/sections/labs-section";
import { OrgInviteCard } from "@/components/portal/sections/org-invite-card";
import { usePortal } from "@/components/portal/portal-context";
import { labLogoUrl } from "@/lib/portal/client";
import { SlackLabCard, TeamsLabCard } from "@/components/portal/ambient/slack-cards";
import {
  useDeleteLabLogo,
  useSetLabDepartmentSees,
  useUploadLabLogo,
} from "@/lib/portal/hooks";
import type { DepartmentSees, MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

/** Owner/admin/PI may edit the lab configuration. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

const ACCEPT = ".png,.jpg,.jpeg,.gif,.webp,.svg,image/png,image/jpeg,image/gif,image/webp,image/svg+xml";
const MAX_BYTES = 2 * 1024 * 1024;

/**
 * The lab configuration surface — the lab workspace's "Lab settings" (the Profile
 * slot in a lab). Manager-only (PI / owner / admin): a non-manager who deep-links
 * here gets an honest permission note.
 *
 * Two-column layout: a narrow left rail of setup cards (logo, invites, connected
 * services, projects) beside a wide right column that leads with the lab's purpose
 * & goals and closes with the member roster as a tile grid. Collapses to one
 * column on small screens.
 *
 * Everything editable about the lab's *profile* lives behind the Edit button in
 * the header, which opens `LabEditorModal` — the same dialog the lab overview and
 * the labs page open, so a lab is configured in exactly one place. The standalone
 * "What Mylo watches" card that used to sit here is gone: it was a read-only
 * restatement of the purpose card's clusters with no way to change the settings
 * it displayed, and its one unique field (cadence) is now a tab in the editor.
 */
export function LabSettingsSection({ lab }: { lab: MyLab }) {
  const { user } = usePortal();
  const [editorTab, setEditorTab] = React.useState<LabEditorTab | null>(null);

  if (!canManageLab(lab)) {
    return (
      <div>
        <SectionHeader eyebrow="Workspace" title="Lab settings" />
        <EmptyState
          icon={<TargetIcon size={28} />}
          title="Only lab managers can edit the lab"
          description="A lab lead, owner, or admin sets the lab's logo, purpose, members, and connections. Ask one of them if you need a change."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        title={`${lab.name} settings`}
        subtitle="Set the lab's logo and purpose, invite members, and connect Mylo."
        action={
          <button
            type="button"
            className={PRIMARY_BUTTON}
            onClick={() => setEditorTab("purpose")}
          >
            <EditIcon size={14} />
            Edit profile
          </button>
        }
      />
      <div className="grid items-start gap-4 lg:grid-cols-[1.5fr_1fr]">
        {/* Left rail — setup cards. The plan lives on the Account page, so nothing
            monetary sits in the middle of configuring the lab. */}
        <div className="space-y-4">
          <LabLogoCard lab={lab} />
          <OrgInviteCard
            kind="lab"
            id={lab.slug}
            canInvite
            isVerified={user.isVerified}
          />
          <DiscordSyncCard lab={lab} />
          <AnnouncementsCard target={{ lab: lab.slug }} name={lab.name} />
          <AgentPolicyCard kind="lab" orgRef={lab.slug} name={lab.name} />
          <SlackLabCard slug={lab.slug} />
          <TeamsLabCard slug={lab.slug} />
          <DiscordHealthCard lab={lab} />
          {lab.department ? <DepartmentSeesCard lab={lab} /> : null}
          <ProjectsCard lab={lab} canManage />
        </div>

        {/* Right column — purpose & goals, then the member roster */}
        <div className="space-y-4">
          <LabPurposeCard
            lab={lab}
            canManage
            onEdit={() => setEditorTab("purpose")}
          />
          <MembersCard lab={lab} grid />
        </div>
      </div>

      {editorTab ? (
        <LabEditorModal
          lab={lab}
          initialTab={editorTab}
          onClose={() => setEditorTab(null)}
        />
      ) : null}
    </div>
  );
}

/** Upload, preview, or remove the lab's logo — shown as its workspace brand mark. */
function LabLogoCard({ lab }: { lab: MyLab }) {
  const upload = useUploadLabLogo(lab.slug);
  const remove = useDeleteLabLogo(lab.slug);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [error, setError] = React.useState<string | null>(null);

  const src = labLogoUrl(lab.slug, lab.logo_version);
  const busy = upload.isPending || remove.isPending;

  function onFile(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError("The logo must be 2 MB or smaller.");
      return;
    }
    upload.mutate(file, { onError: (e) => setError((e as Error).message) });
  }

  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Lab logo
      </h3>
      <div className="flex flex-wrap items-center gap-4">
        <div
          className={cn(
            "flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-surface-alt",
          )}
        >
          {src ? (
            // The logo is served from our own API; a plain img is right here.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt={`${lab.name} logo`}
              className="h-full w-full object-contain"
            />
          ) : (
            <span className="font-serif text-[15px] font-semibold text-[var(--text-secondary)]">
              {lab.name.slice(0, 2).toUpperCase()}
            </span>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={PRIMARY_BUTTON}
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              {upload.isPending
                ? "Uploading…"
                : lab.has_logo
                  ? "Replace logo"
                  : "Upload logo"}
            </button>
            {lab.has_logo ? (
              <button
                type="button"
                className={GHOST_BUTTON}
                onClick={() => {
                  setError(null);
                  remove.mutate(undefined, {
                    onError: (e) => setError((e as Error).message),
                  });
                }}
                disabled={busy}
              >
                <span className="inline-flex items-center gap-1.5">
                  <CloseIcon size={13} />
                  Remove
                </span>
              </button>
            ) : null}
          </div>
          <p className="text-[12px] text-[var(--text-secondary)]">
            PNG, JPG, GIF, WebP, or SVG · up to 2 MB. Shown in the sidebar as the
            lab&apos;s brand mark.
          </p>
          {error ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </Card>
  );
}

const DEPARTMENT_SEES_OPTIONS: {
  value: DepartmentSees;
  label: string;
  hint: string;
}[] = [
  {
    value: "everything",
    label: "Everything",
    hint: "The department's heads can open every project in this lab.",
  },
  {
    value: "names_only",
    label: "Names only",
    hint: "They see each project's name, owner, member count and scope — not its goals, feed, files or team.",
  },
];

/** What the lab's department heads see of its projects. Set here, by the lab's
 * PI / owner / admin — never by the department. A project scoped to the
 * department is seen in full either way. */
function DepartmentSeesCard({ lab }: { lab: MyLab }) {
  const save = useSetLabDepartmentSees(lab.slug);
  const [error, setError] = React.useState<string | null>(null);

  return (
    <Card className="p-5">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        What {lab.department} sees
      </h3>
      <p className="mb-3 text-[12.5px] text-[var(--text-secondary)]">
        Of this lab&apos;s projects, for the department&apos;s heads. Projects
        scoped to the department are always shown in full.
      </p>
      <fieldset className="space-y-2" disabled={save.isPending}>
        <legend className="sr-only">What the department sees</legend>
        {DEPARTMENT_SEES_OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 has-[:checked]:border-primary"
          >
            <input
              type="radio"
              name={`department-sees-${lab.slug}`}
              value={option.value}
              checked={lab.department_sees === option.value}
              onChange={() => {
                setError(null);
                save.mutate(option.value, {
                  onError: (e) => setError((e as Error).message),
                });
              }}
              className="mt-[3px] h-4 w-4 shrink-0 accent-[var(--primary)]"
            />
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold">
                {option.label}
              </span>
              <span className="block text-[12px] text-[var(--text-secondary)]">
                {option.hint}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
      {error ? (
        <p className="mt-2 text-[12.5px] text-clay" role="alert">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
