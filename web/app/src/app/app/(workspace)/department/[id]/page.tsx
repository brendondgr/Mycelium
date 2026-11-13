import { appRedirect } from "@/lib/auth-server";
import { legacySettingsPath } from "@/lib/portal/settings";

/** A department is managed in Settings now; the old page sends you to its General page. */
export default async function DepartmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await appRedirect(legacySettingsPath("department", { id }));
}
