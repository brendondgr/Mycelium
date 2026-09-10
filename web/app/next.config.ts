import path from "node:path";

import type { NextConfig } from "next";

// Pin the Turbopack workspace root to the `web/` monorepo root (one level up
// from this app's cwd, where hoisted node_modules and the workspaces manifest
// live). Without it, Next infers the root from the nearest lockfile, which can
// resolve to a stray parent-directory lockfile and break Turbopack. The app's
// npm scripts always run with cwd = `web/app`, so its parent is `web/`.
const workspaceRoot = path.dirname(process.cwd());

const apiProxyTarget =
  process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

// Next blocks cross-origin requests to dev-only assets and endpoints, so behind
// a reverse proxy or Cloudflare tunnel the external hostname has to be declared
// or dev assets 403. PUBLIC_HOSTNAME (compose → .env) carries it; unset, this
// stays empty and only the default localhost origin is allowed.
const publicHostname = process.env.PUBLIC_HOSTNAME?.trim();

const nextConfig: NextConfig = {
  turbopack: { root: workspaceRoot },
  // The floating Next dev-tools badge (bottom-left) is noise on a deployment
  // that happens to run in dev mode; hide it entirely.
  devIndicators: false,
  allowedDevOrigins: publicHostname ? [publicHostname] : [],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
