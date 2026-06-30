import { WorkspaceShell } from "@/components/portal/workspace-shell";
import type { PortalUser } from "@/components/portal/portal-context";
import { requireOnboardedUser } from "@/lib/auth-server";

export const metadata = {
  title: "Workspace · Mycelium",
  description: "Your lab intelligence dashboard.",
};

/**
 * Shared chrome for every authenticated workspace route. Guards access once
 * here (onboarded users only) so each page can focus on its section content.
 */
export default async function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireOnboardedUser();

  const portalUser: PortalUser = {
    username: user.username,
    email: user.email ?? "",
    name: user.name?.trim() || user.username,
    initials: user.initials?.trim() || user.username.slice(0, 2).toUpperCase(),
    isSuperuser: user.is_superuser,
  };

  return <WorkspaceShell user={portalUser}>{children}</WorkspaceShell>;
}
