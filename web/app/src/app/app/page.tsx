import { Portal } from "@/components/portal/portal";
import type { PortalUser } from "@/components/portal/portal-context";
import { requireOnboardedUser } from "@/lib/auth-server";

export const metadata = {
  title: "Workspace · Mycelium",
  description: "Your lab intelligence dashboard.",
};

export default async function WorkspacePage() {
  const user = await requireOnboardedUser();

  const portalUser: PortalUser = {
    username: user.username,
    email: user.email ?? "",
    name: user.name?.trim() || user.username,
    initials:
      user.initials?.trim() || user.username.slice(0, 2).toUpperCase(),
    isSuperuser: user.is_superuser,
  };

  return <Portal user={portalUser} />;
}
