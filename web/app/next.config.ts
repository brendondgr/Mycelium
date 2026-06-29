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

const nextConfig: NextConfig = {
  turbopack: { root: workspaceRoot },
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
