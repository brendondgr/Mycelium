import { redirect } from "next/navigation";

/** `/app` is an alias for the workspace landing view. */
export default function WorkspaceIndexPage() {
  redirect("/app/overview");
}
