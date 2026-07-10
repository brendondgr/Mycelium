"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { isClientError } from "@/lib/api-error";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Don't retry 4xx (a deauthed 401/403 or a bad request): retrying
            // only fires the same failing request three more times. Keep the
            // default retry budget for transient 5xx/network errors.
            retry: (failureCount, error) =>
              !isClientError(error) && failureCount < 3,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
