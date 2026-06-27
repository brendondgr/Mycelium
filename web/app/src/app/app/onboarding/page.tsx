import { redirect } from "next/navigation";

import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "Set up your workspace · Mycelium",
  description: "Tune your Mycelium research radar.",
};

export default async function OnboardingPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
        <OnboardingFlow email={user.email || "your email address"} />
      </div>
    </main>
  );
}
