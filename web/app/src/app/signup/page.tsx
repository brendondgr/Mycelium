import { redirect } from "next/navigation";

import { SignupForm } from "@/components/auth/signup-form";
import { LoginQuerySanitizer } from "@/components/auth/login-query-sanitizer";
import { MyloMark } from "@/components/brand/mylo-mark";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "Create your account · Mycelium",
  description: "Start your Mycelium research workspace.",
};

export default async function SignupPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect("/app");
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <LoginQuerySanitizer />
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto grid w-full max-w-5xl gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
          <section className="space-y-6">
            <div className="flex items-center gap-3">
              <MyloMark className="h-10 w-9" />
              <p className="text-sm font-medium uppercase tracking-[0.2em] text-primary">
                Mycelium
              </p>
            </div>
            <h1 className="max-w-xl text-4xl font-semibold leading-tight text-[var(--text-primary)] sm:text-5xl">
              Start your workspace in one step.
            </h1>
            <p className="max-w-lg text-lg leading-8 text-[var(--text-secondary)]">
              Choose how you&rsquo;ll work — on your own, leading a lab, or
              running a department. Mylo provisions the rest and tunes your
              research radar during onboarding.
            </p>
            <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
              <li>No credit card — tiers are assigned, never charged yet.</li>
              <li>Onboarding seeds your knowledge graph from your interests.</li>
            </ul>
          </section>

          <section className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <div className="mb-6 space-y-2">
              <h2 className="text-2xl font-semibold text-[var(--text-primary)]">
                Create your account
              </h2>
              <p className="text-sm leading-6 text-[var(--text-secondary)]">
                Pick an account type, then tell us who you are. Session
                authentication is handled by Django.
              </p>
            </div>
            <SignupForm />
          </section>
        </div>
      </div>
    </main>
  );
}
