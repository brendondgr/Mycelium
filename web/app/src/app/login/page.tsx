import { redirect } from "next/navigation";

import { LoginForm } from "@/components/auth/login-form";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "Sign in · Mycelium",
  description: "Sign in to the Mycelium research workspace.",
};

export default async function LoginPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect("/app");
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto grid w-full max-w-5xl gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <section className="space-y-6">
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-primary">
              Mycelium
            </p>
            <h1 className="max-w-xl text-4xl font-semibold leading-tight text-[var(--text-primary)] sm:text-5xl">
              Sign in to your research workspace
            </h1>
            <p className="max-w-lg text-lg leading-8 text-[var(--text-secondary)]">
              Connect papers, people, grants, and evidence-backed plans in one
              living lab memory. Use your lab account credentials to enter the
              private workspace.
            </p>
            <div
              aria-hidden="true"
              className="hidden h-40 max-w-md rounded-2xl border border-border bg-[radial-gradient(circle_at_30%_20%,var(--brand-accent-soft),transparent_55%),linear-gradient(135deg,var(--surface-alt),var(--card))] lg:block"
            />
          </section>

          <section className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <div className="mb-6 space-y-2">
              <h2 className="text-2xl font-semibold text-[var(--text-primary)]">
                Workspace sign-in
              </h2>
              <p className="text-sm leading-6 text-[var(--text-secondary)]">
                Session authentication is handled by Django. No passwords are
                stored in the browser.
              </p>
            </div>
            <LoginForm />
          </section>
        </div>
      </div>
    </main>
  );
}
