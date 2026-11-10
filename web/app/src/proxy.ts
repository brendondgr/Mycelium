import { NextResponse, type NextRequest } from "next/server";

import { DEMO_BASE, DEMO_HEADER } from "@/lib/demo";

/**
 * The public demo's front door (`docs/architecture.md`, "The public demo").
 *
 * `/demo/<x>` renders the workspace page at `/app/<x>` — the same page, the
 * same components — with a request header that tells the server render it is
 * the demo (`lib/auth-server.ts` then reads `/me` through `/api/demo/`). The
 * browser keeps the `/demo/...` URL. `/demo` itself is its own page
 * (`app/demo/page.tsx`), which sends the visitor to the demo lab or 404s when
 * the operator has the demo off.
 *
 * A request that arrives carrying the header from outside is stripped of it,
 * so `/app/*` can never be talked into the demo's identity.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const forwarded = new Headers(request.headers);
  forwarded.delete(DEMO_HEADER);

  if (pathname.startsWith(`${DEMO_BASE}/`)) {
    const url = request.nextUrl.clone();
    url.pathname = `/app${pathname.slice(DEMO_BASE.length)}`;
    forwarded.set(DEMO_HEADER, "1");
    return NextResponse.rewrite(url, { request: { headers: forwarded } });
  }
  return NextResponse.next({ request: { headers: forwarded } });
}

export const config = {
  matcher: ["/demo/:path+", "/app/:path*"],
};
