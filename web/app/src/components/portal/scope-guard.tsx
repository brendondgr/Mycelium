"use client";

import { useEffect } from "react";

import { isPlatformAdmin, usePortal } from "@/components/portal/portal-context";
import { useEntitlements } from "@/lib/portal/hooks";
import { sectionAllowed } from "@/lib/portal/nav";

/**
 * Sends you to the overview when the section you are on is not one the active
 * workspace offers.
 *
 * Hiding the entry from the navigation is not enough on its own. Every feed
 * section is written as `if (currentLab) return <LabFeed/>` and otherwise
 * renders the *personal* feed — so in a department scope, where `currentLab` is
 * null by construction, `/app/grants?ws=<dept>` would quietly show the reader
 * their own personal grants under a department's name. That is the worst class
 * of bug here: not an error, just the wrong answer presented confidently.
 *
 * This is a navigation guard, not a permission boundary. The API decides what
 * anyone may actually read.
 */
export function ScopeGuard() {
  const {
    section,
    scope,
    currentLab,
    currentDepartment,
    goToSection,
    workspacesLoading,
    user,
  } = usePortal();
  const { data: entitlements, isLoading: entitlementsLoading } =
    useEntitlements();

  useEffect(() => {
    // Wait until memberships and entitlements have landed. Guarding early would
    // bounce people off a legitimate page just because the scope had not
    // resolved yet.
    if (workspacesLoading || entitlementsLoading) {
      return;
    }
    const allowed = sectionAllowed(
      {
        scope,
        currentLab,
        currentDepartment,
        isAdmin: isPlatformAdmin(user),
        hasFeature: (feature: string) =>
          !entitlements || entitlements.features.includes(feature),
      },
      section,
    );
    if (!allowed) {
      goToSection("overview");
    }
  }, [
    section,
    scope,
    currentLab,
    currentDepartment,
    user,
    entitlements,
    entitlementsLoading,
    workspacesLoading,
    goToSection,
  ]);

  return null;
}
