"use client";

import { Settings } from "lucide-react";

import {
  BankIcon,
  BellIcon,
  BookmarkIcon,
  ConferenceIcon,
  DocumentIcon,
  FolderIcon,
  GridIcon,
  MembersIcon,
  MyloGlyph,
  ReceiptIcon,
  ShieldIcon,
  SparkleIcon,
  SporeNode,
  TargetIcon,
} from "@/components/portal/icons";
import type { NavIcon } from "@/lib/portal/nav";

/**
 * Resolves the nav model's icon name to a glyph. `lib/portal/nav.ts` stays
 * JSX-free — it decides *what* a scope can reach, not how it is drawn — so the
 * mapping lives here, used by both the sidebar and the mobile sheet.
 */
export function NavIconFor({
  icon,
  size = 18,
}: {
  icon: NavIcon;
  size?: number;
}) {
  switch (icon) {
    case "overview":
      return <GridIcon size={size} />;
    case "profile":
      return <TargetIcon size={size} />;
    case "members":
      return <MembersIcon size={size} />;
    case "labs":
      return <SporeNode size={size} />;
    case "saves":
      return <BookmarkIcon size={size} />;
    case "reminders":
      return <BellIcon size={size} />;
    case "papers":
      return <DocumentIcon size={size} />;
    case "grants":
      return <BankIcon size={size} />;
    case "fellowships":
      return <SparkleIcon size={size} />;
    case "conferences":
      return <ConferenceIcon size={size} />;
    case "projects":
      return <FolderIcon size={size} />;
    case "mylo":
      return <MyloGlyph size={size} />;
    case "admin":
      return <ShieldIcon size={size} />;
    case "account":
      return <ReceiptIcon size={size} />;
    case "settings":
      return <Settings size={size} aria-hidden="true" />;
    default:
      return <GridIcon size={size} />;
  }
}
