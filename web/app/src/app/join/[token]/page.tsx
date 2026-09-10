import { AuthBrandPanel } from "@/components/auth/auth-brand-panel";
import { JoinInvitation } from "@/components/auth/join-invitation";
import { getCurrentUser } from "@/lib/auth-server";

export const metadata = {
  title: "You have been invited · Mycelium",
  description: "Join a lab or department on Mycelium.",
};

/**
 * Where an invitation link lands.
 *
 * Deliberately reachable signed out — the recipient may never have heard of
 * Mycelium, and a page that will not say what it is inviting them to until they
 * have an account is a page nobody makes an account from. The token is read on
 * the client so a withdrawn or expired link can say which, in place rather than
 * as a redirect to a form that will refuse it later.
 */
export default async function JoinPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const user = await getCurrentUser();

  return (
    <main
      className="flex min-h-screen bg-background text-foreground"
      style={{ fontFamily: "var(--font-inter)" }}
    >
      <AuthBrandPanel
        heading="Someone kept a seat for you."
        description="Mycelium reads the literature for a research group and reports what changed. Join the one that invited you and their radar becomes yours."
      />

      <div className="flex flex-1 items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <JoinInvitation token={token} signedIn={Boolean(user)} />
        </div>
      </div>
    </main>
  );
}
