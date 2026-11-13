import { appRedirect } from "@/lib/auth-server";
import { legacySettingsPath } from "@/lib/portal/settings";

/** Account moved into Settings → You → Account. The old link still lands there. */
export default async function AccountPage() {
  await appRedirect(legacySettingsPath("account"));
}
