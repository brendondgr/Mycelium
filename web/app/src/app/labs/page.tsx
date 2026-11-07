import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LabsClient } from "@/components/labs/labs-client";

import "./labs.css";

export const metadata: Metadata = {
  title: "Labs · Mycelium",
  description: "A design playground for the Mycelium workspace.",
  robots: { index: false, follow: false },
};

/**
 * /labs — the workspace design playground.
 *
 * A local tool, not a product surface: it renders fictional data, calls no
 * API, and needs no sign-in. A production build serves it only when
 * `MYCELIUM_LABS=1` is set at runtime; `next dev` (the Compose web service)
 * always serves it.
 */
export const dynamic = "force-dynamic";

export default function LabsPage() {
  if (process.env.NODE_ENV === "production" && process.env.MYCELIUM_LABS !== "1") {
    notFound();
  }
  return <LabsClient />;
}
