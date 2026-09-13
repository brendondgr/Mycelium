/**
 * The affiliation directory: ~10k universities plus the national labs and
 * research institutes, read from a static file rather than an endpoint.
 *
 * Why a file. The directory is reference data that changes when somebody
 * re-runs `web/scripts/build-institutions.mjs`, not when a user does anything.
 * Shipping it as a static asset means the picker has no API surface to
 * authorize, no rate limit to respect, no round trip per keystroke, and it
 * works on paths where the reader has no session yet. It is ~160 KB gzipped,
 * fetched once on the first focus of a picker and cached by the browser after
 * that — never part of the initial page bundle.
 *
 * Why the search is local. Matching a typed fragment against 10k folded
 * strings takes a few milliseconds, so filtering is synchronous and the list
 * cannot lag behind the input the way a debounced endpoint does.
 *
 * Nothing here is authoritative. Hipolabs gives no stable key, so an
 * affiliation is stored as the name string the reader ended up with — whether
 * they picked it from the directory or typed their own. `profile.institution`
 * remains a free string; see `docs/api-contract.md`.
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

/** An entry plus the folded forms the search compares against, computed once
 *  at load so no keystroke pays for them. */
type IndexedInstitution = Institution & {
  folded: string;
  /** The name's words, folded — so "state" can match mid-name. */
  words: string[];
  /** Initials of the significant words: "FSU" finds Florida State University. */
  acronym: string;
};

/** The loaded directory: the rows, plus the two lookups worth precomputing. */
export type InstitutionDirectory = {
  items: IndexedInstitution[];
  /** Every domain that reaches an institution, primary and alternate. */
  byDomain: Map<string, IndexedInstitution>;
  /** Typed shortcuts with no substring path to their target ("mit", "uoft"). */
  byAlias: Map<string, IndexedInstitution>;
};

export type InstitutionMatch = {
  institution: Institution;
  /** Lower is better. Only meaningful for ordering one result set. */
  score: number;
  /** Character range in `institution.name` the query matched, for emphasis. */
  highlight: [number, number] | null;
};

const DATA_URL = "/data/institutions.json";

/** Words that carry no distinguishing signal in an institution name, and so do
 *  not contribute an initial to its acronym. */
const STOPWORDS = new Set([
  "of",
  "the",
  "and",
  "for",
  "at",
  "in",
  "de",
  "di",
  "du",
  "da",
  "des",
  "der",
  "la",
  "le",
  "el",
  "und",
  "y",
]);

/** Lowercase, accents folded, punctuation flattened to single spaces — so
 *  "Université de Montréal" is reachable by typing "universite de montreal". */
export function fold(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function acronymOf(words: string[]): string {
  const significant = words.filter((word) => !STOPWORDS.has(word));
  return significant.length < 2 ? "" : significant.map((word) => word[0]).join("");
}

function indexRow(institution: Institution): IndexedInstitution {
  const folded = fold(institution.name);
  const words = folded.split(" ").filter(Boolean);
  return { ...institution, folded, words, acronym: acronymOf(words) };
}

type RawFile = {
  version: number;
  count: number;
  /** alias -> primary domain. */
  aliases: Record<string, string>;
  /** primary domain -> other domains that reach the same institution. */
  alt_domains: Record<string, string[]>;
  items: [string, string, string, string, number][];
};

let cache: Promise<InstitutionDirectory> | null = null;

/**
 * Fetch and index the directory, once per page load.
 *
 * A failure is not cached: a picker whose first fetch lost the network should
 * succeed on the next focus rather than stay broken for the whole session.
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
  const items = file.items.map((row) =>
    indexRow({
      name: row[0],
      countryCode: row[1],
      domain: row[2],
      region: row[3],
      kind: row[4] === 1 ? "institute" : "university",
    }),
  );

  const byDomain = new Map<string, IndexedInstitution>();
  for (const item of items) {
    // First writer wins: a handful of records share a domain (branch campuses),
    // and the rows are alphabetical, so the choice is at least stable.
    if (!byDomain.has(item.domain)) {
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

  const byAlias = new Map<string, IndexedInstitution>();
  for (const [alias, domain] of Object.entries(file.aliases ?? {})) {
    const item = byDomain.get(domain);
    if (item) {
      byAlias.set(fold(alias), item);
    }
  }

  return { items, byDomain, byAlias };
}

/**
 * Rank the directory against what has been typed so far.
 *
 * The bands, best first: a declared alias ("mit", "uoft" — shortcuts no
 * substring search can reach); the query is the whole name; it is the
 * institution's own acronym ("fsu", "ornl"); it starts the name; it starts a
 * word inside the name ("state" → Florida State University); it starts the
 * email domain; every token of a multi-word query starts some word; it appears
 * anywhere in the name or domain. Inside a band, the shorter name wins — a
 * query is far more often aimed at "Cornell University" than at "Cornell
 * University Weill Medical College".
 *
 * Token matching in any order is what makes "berkeley uni" and "uni berkeley"
 * both work.
 */
export function searchInstitutions(
  directory: InstitutionDirectory,
  query: string,
  limit = 8,
): InstitutionMatch[] {
  const folded = fold(query);
  if (!folded) {
    return [];
  }
  const tokens = folded.split(" ").filter(Boolean);
  const aliased = directory.byAlias.get(folded);
  const scored: { institution: IndexedInstitution; score: number }[] = [];

  if (aliased) {
    scored.push({ institution: aliased, score: -1 });
  }

  for (const item of directory.items) {
    if (item === aliased) {
      continue;
    }
    let score: number | null = null;

    if (item.folded === folded) {
      score = 0;
    } else if (item.acronym === folded) {
      // Above a name prefix on purpose: someone typing "UCSB" means the
      // university whose initials those are, not the first name starting with
      // those four letters. An acronym is a whole identifier matched whole.
      score = 1;
    } else if (item.folded.startsWith(folded)) {
      score = 2;
    } else if (item.words.some((word) => word.startsWith(folded))) {
      score = 3;
    } else if (item.domain.startsWith(folded)) {
      score = 4;
    } else if (
      tokens.length > 1 &&
      tokens.every((token) => item.words.some((word) => word.startsWith(token)))
    ) {
      score = 5;
    } else if (item.folded.includes(folded)) {
      score = 6;
    } else if (item.domain.includes(folded)) {
      score = 7;
    }

    if (score === null) {
      continue;
    }
    scored.push({ institution: item, score });
  }

  scored.sort(
    (a, b) =>
      a.score - b.score ||
      a.institution.name.length - b.institution.name.length ||
      a.institution.name.localeCompare(b.institution.name, "en"),
  );
  // Highlighting is per-character work, so it happens after the cut: a
  // one-letter query matches thousands of entries and only the visible handful
  // is ever marked.
  return scored.slice(0, limit).map((hit) => ({
    institution: hit.institution,
    score: hit.score,
    highlight: highlightRange(hit.institution.name, folded),
  }));
}

/**
 * Where to underline the match in the original, unfolded name.
 *
 * Folding can change a string's length (an accented character decomposes, a
 * run of punctuation collapses), so the range is found by folding a growing
 * prefix rather than by trusting the folded offset. Returns null when the query
 * is not a literal substring — an alias, acronym or multi-token hit has nothing
 * contiguous to mark.
 */
function highlightRange(name: string, foldedQuery: string): [number, number] | null {
  const at = fold(name).indexOf(foldedQuery);
  if (at === -1) {
    return null;
  }
  let start = -1;
  for (let i = 0; i <= name.length; i += 1) {
    const prefix = fold(name.slice(0, i));
    if (start === -1 && prefix.length >= at && prefix.length > 0) {
      start = Math.max(0, i - 1);
    }
    if (start !== -1 && prefix.length >= at + foldedQuery.length) {
      return [start, i];
    }
  }
  return null;
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

/** Does the directory know this exact name? Decides whether what the reader
 *  typed is a directory pick or an affiliation of their own. */
export function isDirectoryName(
  directory: InstitutionDirectory,
  name: string,
): boolean {
  const folded = fold(name);
  return folded !== "" && directory.items.some((item) => item.folded === folded);
}

let regionNames: Intl.DisplayNames | null | undefined;

/** "US" → "United States". Falls back to the bare code where `Intl` has no
 *  region display names, which is nothing a reader needs to be told about. */
export function countryLabel(code: string): string {
  if (regionNames === undefined) {
    try {
      regionNames = new Intl.DisplayNames(["en"], { type: "region" });
    } catch {
      regionNames = null;
    }
  }
  if (!regionNames) {
    return code;
  }
  try {
    return regionNames.of(code) ?? code;
  } catch {
    return code;
  }
}

/** The line under an entry's name: where it is, and the domain that proves it. */
export function institutionCaption(institution: Institution): string {
  const place = [institution.region, countryLabel(institution.countryCode)]
    .filter(Boolean)
    .join(", ");
  return [place, institution.domain].filter(Boolean).join(" · ");
}
