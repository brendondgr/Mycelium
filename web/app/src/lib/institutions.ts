/**
 * The affiliation directory: ~10k universities plus the national labs and
 * research institutes, read from a static file rather than an endpoint.
 *
 * Why a file. The directory is reference data that changes when somebody
 * re-runs `web/scripts/build-institutions.mjs`, not when a user does anything.
 * Shipping it as a static asset means no API surface to authorize, and it works
 * on the sign-up page, where the reader has no session yet. It is ~160 KB
 * gzipped, fetched once on the first valid address and cached by the browser
 * after that — never part of the initial page bundle.
 *
 * Nothing here is authoritative. The backend reads the same file to derive a
 * person's institution from their *verified* email (`apps/accounts/
 * institution.py`); what this module resolves is only a preview of that — the
 * sign-up form's hint. Nobody types an institution; see `docs/api-contract.md`.
 */

export type InstitutionKind = "university" | "institute";

export type Institution = {
  name: string;
  /** ISO 3166-1 alpha-2. */
  countryCode: string;
  /** The email domain people at this institution actually have. */
  domain: string;
  /** State or province. Frequently empty outside the US — do not rely on it. */
  region: string;
  kind: InstitutionKind;
};

/** The loaded directory, indexed by every domain that reaches an institution. */
export type InstitutionDirectory = {
  byDomain: Map<string, Institution>;
};

const DATA_URL = "/data/institutions.json";

type RawFile = {
  version: number;
  count: number;
  /** primary domain -> other domains that reach the same institution. */
  alt_domains: Record<string, string[]>;
  items: [string, string, string, string, number][];
};

let cache: Promise<InstitutionDirectory> | null = null;

/**
 * Fetch and index the directory, once per page load.
 *
 * A failure is not cached: a fetch that lost the network should succeed on the
 * next try rather than stay broken for the whole session.
 */
export function loadInstitutions(): Promise<InstitutionDirectory> {
  if (!cache) {
    cache = fetch(DATA_URL, { cache: "force-cache" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`institution directory: ${response.status}`);
        }
        return response.json() as Promise<RawFile>;
      })
      .then(buildDirectory)
      .catch((error: unknown) => {
        cache = null;
        throw error;
      });
  }
  return cache;
}

function buildDirectory(file: RawFile): InstitutionDirectory {
  const byDomain = new Map<string, Institution>();
  for (const row of file.items) {
    const item: Institution = {
      name: row[0],
      countryCode: row[1],
      domain: row[2],
      region: row[3],
      kind: row[4] === 1 ? "institute" : "university",
    };
    // First writer wins: a handful of records share a domain (branch campuses),
    // and the rows are alphabetical, so the choice is at least stable.
    if (item.domain && !byDomain.has(item.domain)) {
      byDomain.set(item.domain, item);
    }
  }
  for (const [primary, alternates] of Object.entries(file.alt_domains ?? {})) {
    const item = byDomain.get(primary);
    if (!item) continue;
    for (const domain of alternates) {
      if (!byDomain.has(domain)) {
        byDomain.set(domain, item);
      }
    }
  }
  return { byDomain };
}

/**
 * The institution a work address belongs to, or null.
 *
 * Tried exactly first, then by parent domain, so `cs.fsu.edu` and
 * `mail.eng.fsu.edu` both land on Florida State. Free mail hosts are refused
 * outright — nobody's affiliation is Gmail.
 */
export function institutionForEmail(
  directory: InstitutionDirectory,
  email: string,
): Institution | null {
  const at = email.lastIndexOf("@");
  if (at === -1) {
    return null;
  }
  const host = email
    .slice(at + 1)
    .trim()
    .toLowerCase();
  if (!host.includes(".") || FREE_MAIL.has(host)) {
    return null;
  }
  const labels = host.split(".");
  for (let i = 0; i < labels.length - 1; i += 1) {
    const hit = directory.byDomain.get(labels.slice(i).join("."));
    if (hit) {
      return hit;
    }
  }
  return null;
}

const FREE_MAIL = new Set([
  "gmail.com",
  "googlemail.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "yahoo.com",
  "icloud.com",
  "me.com",
  "aol.com",
  "proton.me",
  "protonmail.com",
  "gmx.com",
  "gmx.de",
  "mail.com",
  "yandex.ru",
  "qq.com",
  "163.com",
  "126.com",
]);
