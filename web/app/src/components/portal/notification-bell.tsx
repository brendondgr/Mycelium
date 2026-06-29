"use client";

import { BellIcon } from "@/components/portal/icons";
import { IconButton } from "@/components/portal/primitives/icon-button";

/**
 * Notifications entry point. There is no notification pipeline yet, so the bell
 * carries no fabricated unread dot — it is disabled with an honest label until a
 * real feed exists.
 */
export function NotificationBell() {
  return (
    <IconButton
      label="Notifications — coming soon"
      disabled
      className="cursor-not-allowed opacity-70"
    >
      <BellIcon size={18} />
    </IconButton>
  );
}
