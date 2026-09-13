#!/usr/bin/env node
/**
 * Derive web-ready art for both web surfaces from the canonical PNGs in
 * `web/art/`.
 *
 * The source files are full-resolution masters (1–2 MB each). Shipping those
 * straight to the browser dwarfs everything else on the public site — that page
 * ships no framework JavaScript, so images are the entire payload budget. Each
 * master is therefore resized to the widths it is actually displayed at and
 * encoded as WebP, which typically cuts 1.8 MB to well under 200 kB.
 *
 * Both `web/landing` and `web/app` consume the output, so Mylo looks identical
 * on the marketing pages and inside the workspace, and neither surface carries
 * a hand-copied duplicate that can drift from the master.
 *
 * Run via `npm run sync:assets` (also runs before each workspace's dev and
 * build). Outputs are regenerated only when the master is newer than the
 * derivative, so repeat runs are free. Everything written here is git-ignored —
 * edit the master in `web/art/`, never the derivative.
 */
import { mkdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const webRoot = join(fileURLToPath(new URL(".", import.meta.url)), "..");

/**
 * @type {{ src: string; name: string; out: string; widths: number[]; quality?: number }[]}
 * `widths` are CSS-pixel display widths ×~1.6 for retina headroom; the first
 * entry is the default `src`, the rest feed `srcset`.
 */
const ASSETS = [
  // ---- Public site (web/landing) -----------------------------------------
  {
    // Full-bleed hero background.
    src: "art/frontpage/mylo-hero-rework.png",
    name: "mylo-hero",
    out: "landing/public/images",
    widths: [1600, 900],
    quality: 74,
  },
  {
    // Section background, sitting under a 60–76% cream scrim.
    src: "art/frontpage/ConnectedWorkspace.png",
    name: "connected-workspace",
    out: "landing/public/images",
    widths: [1600, 900],
    quality: 70,
  },
  {
    // Circular portrait, displayed at most ~304 CSS px.
    src: "art/Mylo/MyloHeadshot.png",
    name: "mylo-headshot",
    out: "landing/public/images",
    widths: [512, 256],
    quality: 80,
  },
  {
    // About-page concept art.
    src: "art/logo/ConceptArt.png",
    name: "mylo-concept",
    out: "landing/public/images",
    widths: [900],
    quality: 78,
  },

  // ---- Workspace (web/app) ------------------------------------------------
  {
    // Mylo's portrait carries the mascot everywhere inside the app: the auth
    // brand panel and onboarding at large sizes, the match ring's attribution
    // marker and Mylo's reason note at small ones. One master, four widths.
    //
    // These land at public/ root, not public/images/, because the gateway only
    // proxies single-segment root static files to the app — /images/* is the
    // landing site's own directory (infra/nginx/default.conf).
    src: "art/Mylo/MyloHeadshot.png",
    name: "mylo-portrait",
    out: "app/public",
    widths: [512, 256, 128, 64],
    quality: 82,
  },
];

let written = 0;

for (const { src: srcRel, name, out, widths, quality = 76 } of ASSETS) {
  const src = join(webRoot, srcRel);

  let srcStat;
  try {
    srcStat = statSync(src);
    if (!srcStat.isFile()) {
      throw new Error("not a file");
    }
  } catch {
    console.error(`sync-art-assets: missing source ${srcRel}`);
    process.exit(1);
  }

  for (const width of widths) {
    const destRel = `${out}/${name}-${width}.webp`;
    const dest = join(webRoot, destRel);

    mkdirSync(dirname(dest), { recursive: true });

    try {
      const destStat = statSync(dest);
      if (destStat.isFile() && destStat.mtimeMs >= srcStat.mtimeMs) {
        continue;
      }
    } catch {
      // destination missing — encode below
    }

    const info = await sharp(src)
      .resize({ width, withoutEnlargement: true })
      .webp({ quality })
      .toFile(dest);

    written += 1;
    console.log(
      `sync-art-assets: ${srcRel} -> ${destRel} ` +
        `(${info.width}×${info.height}, ${Math.round(info.size / 1024)} kB)`,
    );
  }
}

if (written === 0) {
  console.log("sync-art-assets: derived images are up to date");
}
