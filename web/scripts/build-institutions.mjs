#!/usr/bin/env node
/**
 * Build the affiliation directory the app's institution picker reads.
 *
 * Two inputs, one output:
 *
 *   Hipolabs `world_universities_and_domains.json` (MIT) — ~10k universities
 *   with country and email domains. It is community-maintained rather than
 *   curated, so it arrives with duplicate spellings of the same school, stray
 *   whitespace, and a `state-province` that is null outside the US more often
 *   than not. Everything below exists to make it presentable.
 *
 *   `data/research-institutions.json` (this repo) — the national labs,
 *   government agencies and independent institutes Hipolabs has no rows for.
 *   Mycelium's readers are not all at universities, and a directory that can
 *   only spell "university" makes the rest of them pick "Custom".
 *
 * The output is a compact, alphabetically sorted, tuple-encoded file committed
 * at `web/app/public/data/institutions.json`. Tuples rather than objects
 * because the key names repeat 10,000 times otherwise; the field order is
 * declared in the file so the reader never has to guess it.
 *
 * Usage:
 *   node web/scripts/build-institutions.mjs               # fetch upstream
 *   node web/scripts/build-institutions.mjs --input x.json # use a local copy
 *   node web/scripts/build-institutions.mjs --check        # fail if stale
 *
 * Re-run it when you want a newer upstream snapshot or you have added an
 * institute by hand. It is deliberately NOT wired into `npm run build`: a
 * production build must not depend on GitHub being up, and a directory that
 * silently changes under a release is a directory nobody can reproduce.
 */

import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");

const UPSTREAM =
  "https://raw.githubusercontent.com/Hipo/university-domains-list/master/world_universities_and_domains.json";
const CURATED = resolve(HERE, "data", "research-institutions.json");
const OUTPUT = resolve(REPO, "web", "app", "public", "data", "institutions.json");

const KIND_UNIVERSITY = 0;
const KIND_INSTITUTE = 1;

/** Names that are the same institution written two ways. Lowercase, accents
 *  folded, punctuation dropped, so "Univ. of X" and "University of X" collide
 *  and only one of them ships. */
function normalizeName(name) {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/\buniv\b\.?/g, "university")
    .replace(/\binst\b\.?/g, "institute")
    .replace(/\btech\b\.?/g, "technology")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/^the\s+/, "")
    .trim();
}

function cleanName(name) {
  return String(name ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanDomain(domain) {
  return String(domain ?? "")
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .replace(/\/.*$/, "");
}

/** Record the other ways to mail an institution, under its primary domain.
 *
 *  Upstream order decides which domain is primary: a record's own first domain
 *  is its main one (`usc.edu` before `isi.edu`, `ethz.ch` before `eth.edu`,
 *  `oxford.ac.uk` before `ox.ac.uk`), and every scheme tried for picking a
 *  "better" one — shortest, most academic suffix — got those exact cases
 *  wrong. The rest stay reachable for address matching. */
function mergeAlternates(alternates, primary, extras) {
  const set = alternates.get(primary) ?? new Set();
  for (const domain of extras) {
    if (domain && domain !== primary) set.add(domain);
  }
  if (set.size > 0) alternates.set(primary, set);
}

async function loadUpstream(inputPath) {
  if (inputPath) {
    return JSON.parse(await readFile(resolve(process.cwd(), inputPath), "utf8"));
  }
  const response = await fetch(UPSTREAM);
  if (!response.ok) {
    throw new Error(`upstream fetch failed: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function main() {
  const args = process.argv.slice(2);
  const checkOnly = args.includes("--check");
  const inputFlag = args.indexOf("--input");
  const inputPath = inputFlag === -1 ? null : args[inputFlag + 1];

  const upstream = await loadUpstream(inputPath);
  const curatedFile = JSON.parse(await readFile(CURATED, "utf8"));
  const curated = curatedFile.institutions;
  const aliasSource = curatedFile.aliases ?? {};

  /** normalized name + country -> row. Curated entries are inserted first so a
   *  hand-written institute is never overwritten by a Hipolabs near-match. */
  const byKey = new Map();
  /** primary domain -> the other domains that reach the same institution, kept
   *  apart from the rows because only ~280 of 10k records have any. They exist
   *  for one job: recognising a work address. Oxford's row says
   *  `oxford.ac.uk`, and its staff write from `ox.ac.uk`. */
  const alternates = new Map();

  const add = (row, kind) => {
    const name = cleanName(row.name);
    const country = String(row.country_code ?? "").trim().toUpperCase();
    const all = (row.domains ?? []).map(cleanDomain).filter((d) => d.includes("."));
    const [primary, ...rest] = all;
    if (name.length < 3 || country.length !== 2 || !primary) return;
    const key = `${normalizeName(name)}|${country}`;
    if (byKey.has(key)) {
      // Same school, second spelling: keep the first row, but let the duplicate
      // contribute its domains — that is how a second spelling earns its keep.
      mergeAlternates(alternates, byKey.get(key)[2], all);
      return;
    }
    byKey.set(key, [name, country, primary, cleanName(row.region ?? ""), kind]);
    mergeAlternates(alternates, primary, rest);
  };

  for (const entry of curated) {
    add({ ...entry, domains: [entry.domain, ...(entry.alt_domains ?? [])] }, KIND_INSTITUTE);
  }
  for (const entry of upstream) {
    add(
      {
        name: entry.name,
        country_code: entry.alpha_two_code,
        region: entry["state-province"] ?? "",
        domains: entry.domains,
      },
      KIND_UNIVERSITY,
    );
  }

  const items = [...byKey.values()].sort(
    (a, b) => a[0].localeCompare(b[0], "en") || a[1].localeCompare(b[1]),
  );

  // Aliases are declared against a domain, not a name: `mit.edu` is stable,
  // while the name it points at is a long string with a spelling Hipolabs may
  // revise. A dangling alias is a build failure — a silently dropped one is a
  // shortcut that stops working with nothing to notice it.
  const domains = new Set(items.map((row) => row[2]));
  const aliases = {};
  const dangling = [];
  for (const [alias, domain] of Object.entries(aliasSource)) {
    if (alias.startsWith("_")) continue;
    if (!domains.has(domain)) {
      dangling.push(`${alias} -> ${domain}`);
      continue;
    }
    aliases[alias.toLowerCase()] = domain;
  }
  if (dangling.length > 0) {
    throw new Error(
      `research-institutions.json declares aliases for domains no longer in the directory:\n  ${dangling.join("\n  ")}`,
    );
  }

  const payload = {
    version: 1,
    generated: new Date().toISOString().slice(0, 10),
    sources: [UPSTREAM, "web/scripts/data/research-institutions.json"],
    fields: ["name", "country_code", "domain", "region", "kind"],
    kinds: { 0: "university", 1: "institute" },
    count: items.length,
    aliases,
    alt_domains: Object.fromEntries(
      [...alternates.entries()]
        .filter(([primary]) => domains.has(primary))
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([primary, set]) => [primary, [...set].sort()]),
    ),
    items,
  };

  // One row per line: a 10k-entry diff is readable, and the file still parses
  // as ordinary JSON.
  const body = `{
  "version": ${payload.version},
  "generated": ${JSON.stringify(payload.generated)},
  "sources": ${JSON.stringify(payload.sources)},
  "fields": ${JSON.stringify(payload.fields)},
  "kinds": ${JSON.stringify(payload.kinds)},
  "count": ${payload.count},
  "aliases": ${JSON.stringify(payload.aliases, null, 4).replace(/\n/g, "\n  ")},
  "alt_domains": {
${Object.entries(payload.alt_domains)
  .map(([primary, list]) => `    ${JSON.stringify(primary)}: ${JSON.stringify(list)}`)
  .join(",\n")}
  },
  "items": [
${items.map((row) => `    ${JSON.stringify(row)}`).join(",\n")}
  ]
}
`;

  if (checkOnly) {
    const current = await readFile(OUTPUT, "utf8").catch(() => "");
    const same =
      createHash("sha256").update(stripGenerated(current)).digest("hex") ===
      createHash("sha256").update(stripGenerated(body)).digest("hex");
    if (!same) {
      console.error("institutions.json is stale — re-run without --check");
      process.exitCode = 1;
      return;
    }
    console.log(`institutions.json is current (${payload.count} entries)`);
    return;
  }

  await mkdir(dirname(OUTPUT), { recursive: true });
  await writeFile(OUTPUT, body, "utf8");
  const merged = curated.length + upstream.length - byKey.size;
  const dropped = byKey.size - items.length;
  console.log(
    `wrote ${OUTPUT}\n  ${payload.count} institutions from ${curated.length} curated + ${upstream.length} upstream rows\n  ${merged} duplicate spellings merged, ${dropped} dropped for having no email domain\n  ${Object.keys(aliases).length} search aliases resolved`,
  );
}

/** `generated` moves every run; it must not make `--check` fail on its own. */
function stripGenerated(text) {
  return text.replace(/"generated":\s*"[^"]*",?/, "");
}

await main();
