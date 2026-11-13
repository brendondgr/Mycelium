import { appRedirect } from "@/lib/auth-server";
import { legacySettingsPath } from "@/lib/portal/settings";

/**
 * Billing lives in Settings: your own subscription under You, a lab's or a
 * department's plan on its Plan page. The route stays as a redirect because it
 * is in people's history and bookmarks.
 */
export default async function BillingPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const ws = (await searchParams).ws;
  await appRedirect(legacySettingsPath("billing", { ws: typeof ws === "string" ? ws : null }));
}
