import Link from "next/link";
import { redirect } from "next/navigation";

import { LogoutButton } from "@/components/auth/logout-button";
import { getCurrentUser } from "@/lib/auth-server";

const workspaceAreas = [
  "Research feed",
  "Lab goals",
  "Grant matches",
  "Knowledge graph",
];

export default async function WorkspacePage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center gap-10 px-6 py-16 sm:px-10 lg:px-12">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-3xl">
            <p className="mb-4 text-sm font-medium uppercase tracking-wide text-primary">
              Lab workspace
            </p>
            <h1 className="text-4xl font-semibold leading-tight text-[var(--text-primary)] sm:text-5xl">
              Welcome back, {user.username}.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-[var(--text-secondary)]">
              You are signed in to the Mycelium authenticated app. Lab-scoped
              data will appear here after membership and permission checks are
              connected—this milestone only confirms your session.
            </p>
            {user.is_superuser ? (
              <p className="mt-3 text-sm text-[var(--text-muted)]">
                Superuser access is active for local smoke testing.
              </p>
            ) : null}
          </div>
          <LogoutButton />
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
              <p className="mt-2 text-sm text-[var(--text-muted)]">
                Placeholder until lab permissions are enforced.
              </p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            href="/login"
          >
            Account portal
          </Link>
          <a
            className="inline-flex min-h-11 items-center rounded-md border border-border bg-secondary px-5 text-sm font-medium text-secondary-foreground hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            href="/api/health/"
          >
            API health
          </a>
        </div>
      </section>
    </main>
  );
}
