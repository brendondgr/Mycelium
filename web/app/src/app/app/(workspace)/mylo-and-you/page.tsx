import { appRedirect } from "@/lib/auth-server";
import { legacySettingsPath } from "@/lib/portal/settings";

/** Mylo & you moved into Settings → You. */
export default async function MyloAndYouPage() {
  await appRedirect(legacySettingsPath("mylo"));
}
