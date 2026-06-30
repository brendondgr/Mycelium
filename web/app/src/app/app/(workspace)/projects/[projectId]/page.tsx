import { ProjectDetailSection } from "@/components/portal/sections/project-detail-section";

export const metadata = { title: "Project · Mycelium" };

// The active project id is read from the URL via the portal context, so the
// detail section needs no props — the `[projectId]` segment drives it.
export default function ProjectDetailPage() {
  return <ProjectDetailSection />;
}
