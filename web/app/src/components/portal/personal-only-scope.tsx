"use client";

import * as React from "react";

/**
 * Marks a subtree whose saves and reminders stay with the person: the inside of
 * an `invite_only` project. A lab save or a lab-channel reminder made from there
 * would tell the whole lab what the project is looking at, so the save menu and
 * the reminder composer offer only the personal option (scoping plan, Phase 4).
 * The API refuses the lab option too when it is sent a `project_id`.
 */
const PersonalOnlyContext = React.createContext(false);

export function PersonalOnlyScope({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <PersonalOnlyContext.Provider value={active}>
      {children}
    </PersonalOnlyContext.Provider>
  );
}

/** Whether lab saves and lab-channel reminders are withheld here. */
export function usePersonalOnly(): boolean {
  return React.useContext(PersonalOnlyContext);
}
