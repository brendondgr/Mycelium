"use client";

import dynamic from "next/dynamic";

/**
 * The studio reads its saved choices from localStorage on first render, which
 * the server cannot see — so it is rendered on the client only rather than
 * hydrated from a default and then swapped.
 */
export const LabsClient = dynamic(
  () => import("@/components/labs/labs-studio").then((m) => m.LabsStudio),
  {
    ssr: false,
    loading: () => <div className="lx-studio" aria-busy="true" />,
  },
);
