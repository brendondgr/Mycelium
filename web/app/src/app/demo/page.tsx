import { notFound, redirect } from "next/navigation";

import { buildApiUrl, getServerApiBase } from "@/lib/api-url";

export const dynamic = "force-dynamic";

/**
 * `/demo`: the public demo's entry. Asks the backend whether the demo is on
 * (`GET /api/demo/status/`, 404 when the operator has it off or no world is
 * built) and sends the visitor into the demo lab's overview.
 */
export default async function DemoEntry() {
  let entry: string | null = null;
  try {
    const response = await fetch(buildApiUrl(getServerApiBase(), "demo", "status"), {
      cache: "no-store",
    });
    if (response.ok) {
      const body = (await response.json()) as { enabled?: boolean; entry?: string };
      if (body.enabled === true && typeof body.entry === "string") {
        entry = body.entry;
      }
    }
  } catch {
    entry = null;
  }
  if (!entry || !entry.startsWith("/demo/")) {
    notFound();
  }
  redirect(entry);
}
