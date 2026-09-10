import { redirect } from "next/navigation";

import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "Set up your workspace · Mycelium",
  description: "Tune your Mycelium research radar.",
};

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ edit?: string | string[] }>;
}) {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  // `?edit=1` re-enters the flow to revise an existing profile; the one-time
  // gate only redirects finished users when they are *not* editing.
  const editing = Boolean((await searchParams).edit);
  if (user.onboarding_completed && !editing) {
    redirect("/app/overview");
  }

  return (
    <main
      className="min-h-screen overflow-x-hidden bg-background text-foreground"
      style={{ fontFamily: "var(--font-inter)" }}
    >
      <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
        <OnboardingFlow
          email={user.email || "your email address"}
          mode={editing ? "edit" : "onboard"}
          verified={Boolean(user.is_verified)}
        />
      </div>
    </main>
  );
}
