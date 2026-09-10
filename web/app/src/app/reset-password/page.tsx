import { Suspense } from "react";

import { AuthBrandPanel } from "@/components/auth/auth-brand-panel";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export const metadata = {
  title: "Choose a new password · Mycelium",
  description: "Set a new password for your Mycelium account.",
};

/**
 * Where the emailed reset link lands. Deliberately not redirecting a signed-in
 * visitor away: someone can be signed in on one tab and following a reset link
 * in another, and bouncing them would strand a link they only get once.
 */
export default function ResetPasswordPage() {
  return (
    <main
      className="flex min-h-screen bg-background text-foreground"
      style={{ fontFamily: "var(--font-inter)" }}
    >
      <AuthBrandPanel
        heading="Choose something only you know."
        description="Setting a new password signs out every other device that was using the old one."
      />

      <div className="flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
        <div className="w-full max-w-sm">
          <h2 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
            Set a new password
          </h2>
          <div className="mt-7">
            {/* useSearchParams needs a suspense boundary to prerender. */}
            <Suspense fallback={null}>
              <ResetPasswordForm />
            </Suspense>
          </div>
        </div>
      </div>
    </main>
  );
}
