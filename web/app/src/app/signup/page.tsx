import { redirect } from "next/navigation";

import { AuthBrandPanel } from "@/components/auth/auth-brand-panel";
import { SignupForm } from "@/components/auth/signup-form";
import { LoginQuerySanitizer } from "@/components/auth/login-query-sanitizer";
import { getCurrentUser, getSignupPolicy } from "@/lib/auth-server";

export const metadata = {
  title: "Create your account · Mycelium",
  description: "Start your Mycelium research workspace.",
};

const CHECKLIST = [
  "Open source — nothing to pay",
  "Onboarding tunes your research radar instantly",
  "Start a lab or department later, once you are in",
];

export default async function SignupPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect("/app/overview");
  }
  const policy = await getSignupPolicy();

  return (
    <main
      className="flex min-h-screen bg-background text-foreground"
      style={{ fontFamily: "var(--font-inter)" }}
    >
      <LoginQuerySanitizer />

      <AuthBrandPanel
        heading="Start your workspace in one step."
        description="Tell Mylo who you are and what you work on. Labs and departments come later, once you have seen what the radar does for you alone."
      >
        <ul className="space-y-3">
          {CHECKLIST.map((item) => (
            <li
              key={item}
              className="flex items-center gap-3 text-sm text-brand-panel-foreground/85"
            >
              <span
                aria-hidden="true"
                className="flex h-6 w-6 flex-none items-center justify-center rounded-full"
                style={{
                  background:
                    "color-mix(in srgb, var(--brand-secondary) 22%, transparent)",
                }}
              >
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                >
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </span>
              {item}
            </li>
          ))}
        </ul>
      </AuthBrandPanel>

      <div className="flex flex-1 items-start justify-center overflow-y-auto px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <h2 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
            Create your account
          </h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Tell us who you are. You can start a lab or department once you are
            in.
          </p>
          <div className="mt-7">
            <SignupForm policy={policy} />
          </div>
        </div>
      </div>
    </main>
  );
}
