"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { logout } from "@/lib/auth-client";

export function LogoutButton() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogout() {
    setIsLoading(true);
    setError(null);

    try {
      await logout();
      router.replace("/login");
      router.refresh();
    } catch (logoutError) {
      setIsLoading(false);
      setError(
        logoutError instanceof Error
          ? logoutError.message
          : "Could not sign out.",
      );
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        disabled={isLoading}
        onClick={handleLogout}
        type="button"
        variant="secondary"
      >
        {isLoading ? "Signing out…" : "Sign out"}
      </Button>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
