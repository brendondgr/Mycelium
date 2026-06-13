import path from "node:path";
import { fileURLToPath } from "node:url";
import mdx from "@astrojs/mdx";
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  integrations: [mdx(), react()],
  vite: {
    plugins: [tailwindcss()],
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
