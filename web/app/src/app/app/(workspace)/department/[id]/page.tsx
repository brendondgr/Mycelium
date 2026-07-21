import { DepartmentSection } from "@/components/portal/sections/department-section";

export const metadata = { title: "Department · Mycelium" };

// The department id is read from the `[id]` segment inside the section (client),
// mirroring how the project detail page drives itself from the URL.
export default function DepartmentPage() {
  return <DepartmentSection />;
}
