import { redirect } from "next/navigation";

import { AuthBrandPanel } from "@/components/auth/auth-brand-panel";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "Reset your password · Mycelium",
  description: "Ask for a link to set a new Mycelium password.",
};

export default async function ForgotPasswordPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect("/app/account");
  }

  return (
    <main
      className="flex min-h-screen bg-background text-foreground"
      style={{ fontFamily: "var(--font-inter)" }}
    >
      <AuthBrandPanel
        heading="Locked out is temporary."
        description="Tell us the address on your account and we will send a link that lets you choose a new password."
      />

      <div className="flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
        <div className="w-full max-w-sm">
          <h2 className="font-serif text-3xl font-semibold text-[var(--text-primary)]">
            Forgot your password?
          </h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            We will email you a link to set a new one.
          </p>
          <div className="mt-7">
            <ForgotPasswordForm />
          </div>
        </div>
      </div>
    </main>
  );
}
