import { Button } from "@/components/ui/button";
import Link from "next/link";

const workspaceAreas = [
  "Research feed",
  "Lab goals",
  "Grant matches",
  "Knowledge graph",
];

export default function WorkspacePage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center gap-10 px-6 py-16 sm:px-10 lg:px-12">
        <div className="max-w-3xl">
          <p className="mb-4 text-sm font-medium uppercase tracking-wide text-primary">
            Lab workspace
          </p>
          <h1 className="text-4xl font-semibold leading-tight text-[var(--text-primary)] sm:text-6xl">
            Dynamic research operations live here.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-[var(--text-secondary)]">
            This Next.js app is the authenticated side of Mycelium: dashboards,
            tables, forms, graph views, motion-rich workflows, and Django API
            integrations.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {workspaceAreas.map((area) => (
            <div
              key={area}
              className="rounded-lg border border-border bg-card p-5 shadow-sm"
            >
              <p className="text-base font-medium text-card-foreground">
                {area}
              </p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/">Back to app home</Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <a
              href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api"}/health/`}
            >
              API health
            </a>
          </Button>
        </div>
      </section>
    </main>
  );
}
