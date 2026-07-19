"use client";

import {
  BankIcon,
  BookmarkIcon,
  ConferenceIcon,
  DocumentIcon,
  GridIcon,
  MembersIcon,
  ShieldIcon,
  SparkleIcon,
  SporeNode,
  TargetIcon,
} from "@/components/portal/icons";
import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { ProjectsNav } from "@/components/portal/projects-nav";
import { SidebarNavItem } from "@/components/portal/sidebar-nav-item";
import { labLogoUrl } from "@/lib/portal/client";
import { useEntitlements } from "@/lib/portal/hooks";
import { FEATURE, type MyLab } from "@/lib/portal/types";

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 px-3.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/** A member with owner/admin/PI rights may edit the lab configuration. */
function canManageLab(lab: MyLab): boolean {
  return lab.is_lead || lab.role === "owner" || lab.role === "admin";
}

/**
 * The lab workspace's brand block: the uploaded logo centered (or the lab name in
 * text when there's no logo), plus a green "Lab workspace" pill — the clear cue
 * that you're in a lab, not your personal space.
 */
function LabIdentity({ lab }: { lab: MyLab }) {
  const src = labLogoUrl(lab.slug, lab.logo_version);
  return (
    <div className="mb-5 flex flex-col items-center gap-2 px-2 pt-1 text-center">
      {src ? (
        // The logo is user-supplied and served from our own API; a plain img is right.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={`${lab.name} logo`}
          className="h-12 w-auto max-w-[150px] rounded-lg object-contain"
        />
      ) : (
        <span className="font-serif text-[18px] font-semibold leading-tight text-[var(--text-primary)]">
          {lab.name}
        </span>
      )}
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[color-mix(in_srgb,var(--primary)_13%,transparent)] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.07em] text-primary">
        <SporeNode size={11} />
        Lab workspace
      </span>
    </div>
  );
}

/** The subtle personal-space marker (mirrors the lab identity block). */
function PersonalIdentity() {
  return (
    <div className="mb-4 px-1 pt-1">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-alt px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">
        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
        Personal workspace
      </span>
    </div>
  );
}

/** The left workspace navigation (desktop). Mobile uses a separate tab strip. */
export function PortalSidebar() {
  const { section, goToSection, currentLab, user } = usePortal();
  const { data: entitlements } = useEntitlements();
  // Personal research entries only populate on a paid personal plan; a lab is on
  // its own (paid) plan, so lab research entries are always shown to members.
  const has = (feature: string) =>
    !entitlements || entitlements.features.includes(feature);

  const inLab = Boolean(currentLab);
  const manageLab = currentLab ? canManageLab(currentLab) : false;

  return (
    <aside className="hidden h-full w-[244px] shrink-0 overflow-y-auto border-r border-[var(--divider)] px-3.5 pb-6 pt-[18px] lg:block">
      {inLab && currentLab ? (
        <LabIdentity lab={currentLab} />
      ) : (
        <PersonalIdentity />
      )}

      <GroupLabel>Workspace</GroupLabel>
      <nav className="mb-[18px] flex flex-col gap-0.5">
        <SidebarNavItem
          icon={<GridIcon size={18} />}
          label="Overview"
          active={section === "overview"}
          onClick={() => goToSection("overview")}
        />
        {inLab ? (
          <>
            <SidebarNavItem
              icon={<MembersIcon size={18} />}
              label="Members"
              active={section === "members"}
              onClick={() => goToSection("members")}
            />
            {manageLab ? (
              <SidebarNavItem
                icon={<TargetIcon size={18} />}
                label="Lab settings"
                active={section === "profile"}
                onClick={() => goToSection("profile")}
              />
            ) : null}
          </>
        ) : (
          <SidebarNavItem
            icon={<TargetIcon size={18} />}
            label="Profile"
            active={section === "profile"}
            onClick={() => goToSection("profile")}
          />
        )}
        <SidebarNavItem
          icon={<BookmarkIcon size={18} />}
          label="Saves"
          active={section === "saves"}
          onClick={() => goToSection("saves")}
        />
      </nav>

      <GroupLabel>Research</GroupLabel>
      <nav className="flex flex-col gap-0.5">
        {!inLab ? (
          <SidebarNavItem
            icon={<SporeNode size={18} />}
            label="Suggested for you"
            active={section === "suggested"}
            onClick={() => goToSection("suggested")}
          />
        ) : null}
        <SidebarNavItem
          icon={<DocumentIcon size={18} />}
          label="Research Papers"
          active={section === "papers"}
          onClick={() => goToSection("papers")}
        />
        {inLab || has(FEATURE.GRANT_ALERTS) ? (
          <SidebarNavItem
            icon={<BankIcon size={18} />}
            label="Grants"
            active={section === "opportunities"}
            onClick={() => goToSection("opportunities")}
          />
        ) : null}
        {inLab || has(FEATURE.FELLOWSHIP_MATCHING) ? (
          <SidebarNavItem
            icon={<SparkleIcon size={18} />}
            label="Fellowships"
            active={section === "fellowships"}
            onClick={() => goToSection("fellowships")}
          />
        ) : null}
        {inLab || has(FEATURE.CONFERENCE_ALERTS) ? (
          <SidebarNavItem
            icon={<ConferenceIcon size={18} />}
            label="Conferences"
            active={section === "conferences"}
            onClick={() => goToSection("conferences")}
          />
        ) : null}
        <ProjectsNav />
      </nav>

      {/* Personal-workspace admin surface — only staff/superusers see it, and only
          in the personal scope (it manages platform users, not a lab). */}
      {!inLab && isPlatformAdmin(user) ? (
        <div className="mt-[18px]">
          <GroupLabel>Admin</GroupLabel>
          <nav className="flex flex-col gap-0.5">
            <SidebarNavItem
              icon={<ShieldIcon size={18} />}
              label="Admin dashboard"
              active={section === "admin"}
              onClick={() => goToSection("admin")}
            />
          </nav>
        </div>
      ) : null}
    </aside>
  );
}
