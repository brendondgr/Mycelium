import { appRedirect } from "@/lib/auth-server";

/** `/app` is an alias for the workspace landing view. */
export default async function WorkspaceIndexPage() {
  await appRedirect("/app/overview");
}
