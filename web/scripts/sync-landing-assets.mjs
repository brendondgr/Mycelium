#!/usr/bin/env node
/**
 * Copy canonical art assets into the Astro landing public directory.
 * Run via `npm run sync:assets` (also runs before dev and build).
 */
import { copyFileSync, mkdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = join(fileURLToPath(new URL(".", import.meta.url)), "..");

/** @type {{ src: string; dest: string }[]} */
const ASSETS = [
  {
    src: "art/frontpage/MyloHero.png",
    dest: "landing/public/images/mylo-hero.png",
  },
  {
    src: "art/frontpage/ConnectedWorkspace.png",
    dest: "landing/public/images/connected-workspace.png",
  },
];

let copied = 0;

for (const { src: srcRel, dest: destRel } of ASSETS) {
  const src = join(webRoot, srcRel);
  const dest = join(webRoot, destRel);

  let srcStat;
  try {
    srcStat = statSync(src);
    if (!srcStat.isFile()) {
      throw new Error("not a file");
    }
  } catch {
    console.error(`sync-landing-assets: missing source ${srcRel}`);
    process.exit(1);
  }

  mkdirSync(dirname(dest), { recursive: true });

  let skip = false;
  try {
    const destStat = statSync(dest);
    if (
      destStat.isFile() &&
      destStat.mtimeMs >= srcStat.mtimeMs &&
      destStat.size === srcStat.size
    ) {
      skip = true;
    }
  } catch {
    // destination missing — copy below
  }

  if (skip) {
    continue;
  }

  copyFileSync(src, dest);
  copied += 1;
  console.log(`sync-landing-assets: ${srcRel} -> ${destRel}`);
}

if (copied === 0) {
  console.log("sync-landing-assets: landing public images are up to date");
}
