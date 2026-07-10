import { Suspense } from "react";

import { SearchSection } from "@/components/portal/sections/search-section";

export const metadata = { title: "Search · Mycelium" };

export default function SearchPage() {
  // SearchSection reads the query/filters from the URL (useSearchParams), which
  // must sit under a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <SearchSection />
    </Suspense>
  );
}
