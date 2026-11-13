import { appRedirect } from "@/lib/auth-server";
import { legacySettingsPath } from "@/lib/portal/settings";

/**
 * The old Profile route. It used to show your own profile, or a lab's settings
 * when `?ws=` named a lab, so the parameter picks the Settings context once. A
 * Discord or Slack link attempt configured to return here keeps its outcome.
 */
export default async function ProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const one = (key: string) => (typeof params[key] === "string" ? (params[key] as string) : null);
  await appRedirect(
    legacySettingsPath("profile", {
      ws: one("ws"),
      returned: { discord: one("discord"), slack: one("slack") },
    }),
  );
}
