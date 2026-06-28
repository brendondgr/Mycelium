import { redirect } from "next/navigation";

import { AuthBrandPanel } from "@/components/auth/auth-brand-panel";
import { LoginForm } from "@/components/auth/login-form";
import { LoginQuerySanitizer } from "@/components/auth/login-query-sanitizer";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "Sign in · Mycelium",
  description: "Sign in to the Mycelium research workspace.",
};

const QUOTES: { text: string; tone: "green" | "gold" }[] = [
  { text: "I found 12 papers relevant to your lab goals.", tone: "green" },
  { text: "This fellowship matches your profile and timeline.", tone: "gold" },
  { text: "Your knowledge graph has 18 new connections.", tone: "green" },
];

export default async function LoginPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect("/app");
  }

  return (
    <main
      className="flex min-h-screen bg-background text-foreground"
      style={{ fontFamily: "var(--font-inter)" }}
    >
      <LoginQuerySanitizer />

      <AuthBrandPanel
        heading="Your research, woven into a living network."
        description="Mylo scouts the literature, surfaces grants and fellowships on time, and keeps your lab's knowledge graph growing while you work."
      >
        <ul className="space-y-3">
          {QUOTES.map((quote) => (
            <li
              key={quote.text}
              className="flex items-center gap-3 text-sm text-brand-panel-foreground/85"
            >
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 flex-none rounded-full"
                style={{
                  background:
                    quote.tone === "gold"
                      ? "var(--brand-accent)"
                      : "var(--brand-secondary)",
                }}
              />
              &ldquo;{quote.text}&rdquo;
            </li>
          ))}
        </ul>
      </AuthBrandPanel>

      <div className="flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
        <div className="w-full max-w-sm">
          <h2 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
            Welcome back
          </h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Sign in to your research workspace.
          </p>
          <div className="mt-7">
            <LoginForm />
          </div>
        </div>
      </div>
    </main>
  );
}
