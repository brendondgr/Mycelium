"use client";

import { Avatar } from "@/components/portal/primitives/avatar";
import { Pill } from "@/components/portal/primitives/pill";
import type { LabMember } from "@/lib/portal/types";

/** Capitalise the first letter of a role string for display. */
function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function MemberRow({ member }: { member: LabMember }) {
  const roleDisplay = member.is_lead ? "PI" : capitalize(member.role);

  return (
    <div className="flex items-center gap-3.5 border-b border-[var(--divider)] px-5 py-3.5 hover:bg-surface-alt">
      <Avatar
        initials={member.initials}
        seed={member.username}
        size={36}
      />

      {/* Name + role */}
      <div className="min-w-0 flex-1">
        <p className="m-0 truncate text-sm font-medium text-[var(--text-primary)]">
          {member.name}
        </p>
        <p className="m-0 text-xs text-[var(--text-secondary)]">{roleDisplay}</p>
      </div>

      {/* Email — hidden on small screens */}
      <span className="hidden text-xs text-[var(--text-secondary)] sm:block">
        {member.email}
      </span>

      {/* Lead PIs get a highlight pill; the role already shows under the name. */}
      {member.is_lead ? <Pill tone="primary">PI</Pill> : null}
    </div>
  );
}
