import path from "node:path";
import { fileURLToPath } from "node:url";
import mdx from "@astrojs/mdx";
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

const root = path.dirname(fileURLToPath(import.meta.url));

// Vite's dev server rejects any Host header it was not started with, so behind
// a reverse proxy or Cloudflare tunnel every request comes back as "Blocked
// request. This host is not allowed." PUBLIC_HOSTNAME (compose → .env) names
// the external hostname; unset, this stays empty and only localhost is served.
const publicHostname = process.env.PUBLIC_HOSTNAME?.trim();

export default defineConfig({
  integrations: [mdx(), react()],
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
