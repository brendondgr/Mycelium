import path from "node:path";
import { fileURLToPath } from "node:url";
import mdx from "@astrojs/mdx";
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

const root = path.dirname(fileURLToPath(import.meta.url));

// Vite's dev server (`make dev`) rejects any Host header it was not started
// with, so behind a reverse proxy or Cloudflare tunnel every request comes back
// as "Blocked request. This host is not allowed." PUBLIC_HOSTNAME (compose →
// .env) names the external hostname; unset, this stays empty and only
// localhost is served. Production serves the static build, so this is dev-only.
const publicHostname = process.env.PUBLIC_HOSTNAME?.trim();

export default defineConfig({
  // ./dist by default. compose.yaml copies it into the volume nginx serves:
  // Astro moves its output with a rename, which cannot cross filesystems, so
  // ASTRO_OUT_DIR must stay on the same filesystem as this project.
  outDir: process.env.ASTRO_OUT_DIR?.trim() || "./dist",
  integrations: [mdx(), react()],
  // The pricing page was removed when Mycelium moved to an open-source
  // release; old links land on the front page rather than a 404.
  redirects: {
    "/pricing": "/",
  },
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: publicHostname ? [publicHostname] : [],
    },
    resolve: {
      alias: {
        "@mycelium/config/theme.css": path.resolve(
          root,
          "../packages/config/src/theme.css",
        ),
      },
    },
  },
});
