import Link from "next/link";

import { requireOnboardedUser } from "@/lib/auth-server";

type LabDashboardPageProps = {
  params: Promise<{ labSlug: string }>;
};

export default async function LabDashboardPage({ params }: LabDashboardPageProps) {
  await requireOnboardedUser();
  const { labSlug } = await params;

  return (
    <main className="min-h-screen bg-background px-6 py-16 text-foreground">
      <div className="mx-auto max-w-2xl">
        <p className="text-sm font-medium uppercase tracking-wide text-primary">
          Lab workspace
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
          {labSlug}
        </h1>
        <p className="mt-4 text-[var(--text-secondary)]">
          Lab-scoped dashboards will appear here after membership and permission
          checks are wired to real data.
        </p>
        <Link
          className="mt-8 inline-flex min-h-11 items-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="/app/overview"
        >
          Back to workspace
        </Link>
      </div>
    </main>
  );
}
