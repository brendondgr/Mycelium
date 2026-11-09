/**
 * A venue's short name, for the one line a feed card gives it.
 *
 * Indexes hand back the whole masthead: "ATLAS — CERN European Organization
 * for Nuclear Research", "Clinical microbiology and infection : the official
 * publication of the European Society of …", "Proceedings of the 49th
 * International ACM SIGIR Conference on …". A card wants "ATLAS",
 * "Clinical microbiology and infection", "SIGIR". The full string stays in the
 * opened item's source row and in the line's tooltip, so nothing is lost —
 * this only decides what fits on one line.
 */

/** Organisations that prefix an acronym but are never the venue itself. */
const PUBLISHERS = new Set(["ACM", "IEEE", "IFIP", "AAAI", "SIAM", "USENIX", "ISCA", "ACL", "IAPR", "SPIE"]);

const SEPARATORS = [" : ", ": ", " = ", " — ", " – ", " - ", " | "];

/** "NeurIPS", "FOPAM", "IJID" — a short token with at least two capitals. */
function looksLikeAcronym(token: string): boolean {
  return (
    token.length >= 2 &&
    token.length <= 12 &&
    /^[A-Za-z][A-Za-z0-9&-]*$/.test(token) &&
    (token.match(/[A-Z]/g) ?? []).length >= 2
  );
}

export function shortVenue(venue: string | null | undefined): string {
  const full = (venue ?? "").replace(/\s+/g, " ").trim();
  if (!full) return "";

  // A parenthesised acronym is the venue's own short name:
  // "Advances in Neural Information Processing Systems (NeurIPS)".
  const paren = full.match(/\(([^()]+)\)\s*$/);
  if (paren) {
    const inner = paren[1].replace(/\b(19|20)\d{2}\b/g, "").trim();
    if (looksLikeAcronym(inner)) return inner;
  }

  // "Proceedings of the 49th International ACM SIGIR Conference on …" → "SIGIR".
  if (/^proceedings\b/i.test(full)) {
    const acronym = full
      .split(/[\s,/]+/)
      .find((t) => looksLikeAcronym(t) && !PUBLISHERS.has(t) && t === t.toUpperCase());
    if (acronym) return acronym;
  }

  // The name before a subtitle, an alternate-language title or an affiliation.
  let head = full;
  for (const sep of SEPARATORS) {
    const at = head.indexOf(sep);
    if (at > 0) head = head.slice(0, at);
  }
  // "Journal of Animal Science and Biotechnology/Journal of animal …".
  const slash = head.indexOf("/");
  if (slash > 8) head = head.slice(0, slash);

  // "arXiv (Cornell University)": an affiliation in brackets is not the name.
  head = head.replace(/\s*\([^()]*\)\s*$/, "").trim() || head;
  // "The journal of …" → "Journal of …"; a name that starts lower-case on its
  // own ("arXiv", "bioRxiv") keeps its spelling.
  if (/^the\s+/i.test(head)) {
    const rest = head.replace(/^the\s+/i, "");
    head = rest[0].toUpperCase() + rest.slice(1);
  }
  return head || full;
}
