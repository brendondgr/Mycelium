"""Turn whatever a caller sends into explicit identifiers.

Pure parsing, no network. Accepts a bare string ("31234567", "PMC7286232",
"10.1016/j.watres.2020.116073", "doi:...", any PubMed / PMC / Europe PMC /
doi.org / publisher URL, an arXiv id old or new style) or a dict with explicit
fields. Anything that is not recognisably an identifier but looks like prose
is treated as a title to search for.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"'<>]+)", re.I)
PMCID_RE = re.compile(r"^PMC\d{1,10}$", re.I)
PMID_RE = re.compile(r"^\d{1,9}$")
PII_RE = re.compile(r"/pii/([SB]?[0-9X]{15,17})", re.I)
# arXiv ids: new style YYMM.NNNNN (4 digits after the dot before 2015), old style
# archive[.SUBJECT-CLASS]/YYMMNNN. The month is checked because a single
# malformed id makes the arXiv API answer an error for a whole batch.
_YYMM = r"\d{2}(?:0[1-9]|1[0-2])"
ARXIV_RE = re.compile(
    rf"^(?:arxiv:\s*)?(?:({_YYMM}\.\d{{4,5}})|([a-z]+(?:-[a-z]+)?)(?:\.[a-z-]+)?"
    rf"/({_YYMM}\d{{3}}))(v\d+)?(?:\.pdf)?/?$",
    re.I,
)
PREFIX_RE = re.compile(r"^(pmid|pmcid|pmc|doi|pii)\s*[:=]?\s*", re.I)

URL_PATTERNS = [
    (re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,9})"), "pmid"),
    (re.compile(r"ncbi\.nlm\.nih\.gov/pubmed/(\d{1,9})"), "pmid"),
    (re.compile(r"ncbi\.nlm\.nih\.gov/(?:pmc/)?articles/(PMC\d+)", re.I), "pmcid"),
    (re.compile(r"europepmc\.org/(?:abstract|article)/MED/(\d{1,9})", re.I), "pmid"),
    (re.compile(r"europepmc\.org/(?:abstract|article)/PMC/(PMC\d+)", re.I), "pmcid"),
    (re.compile(r"arxiv\.org/(?:abs|pdf|html)/([^?#]+)", re.I), "arxiv"),
]


def clean_doi(raw: str) -> str:
    """Normalise a DOI: drop resolver prefixes, URL-encoding, trailing
    punctuation; lowercase (DOIs are case-insensitive)."""
    doi = unquote(raw.strip())
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    m = DOI_RE.search(doi)
    if not m:
        return ""
    doi = m.group(1)
    # Strip punctuation that trails a DOI pasted from prose, but keep balanced
    # parentheses, which Elsevier DOIs use: 10.1016/s1085-5629(99)80036-4.
    while (
        doi
        and doi[-1] in ".,;:]}>\"'"
        or (doi.endswith(")") and doi.count(")") > doi.count("("))
    ):
        doi = doi[:-1]
    # Publisher URLs append path segments after the DOI (/full, /pdf, /abstract).
    doi = re.sub(r"/(full|pdf|epdf|abstract|fulltext|html|meta)$", "", doi, flags=re.I)
    return doi.lower()


def parse_arxiv(text: str) -> tuple[str, list[str]] | None:
    """(DataCite DOI, notes) for an arXiv id in any common spelling, else None.

    'arXiv:2101.00001v2', 'hep-th/9901001', 'math.GT/0309136' (the subject
    class is not part of the id) -> 10.48550/arxiv.2101.00001, ...
    """
    m = ARXIV_RE.match(text.strip())
    if not m:
        return None
    new, archive, number, version = m.groups()
    aid = new or f"{archive.lower()}/{number}"
    doi = f"10.48550/arxiv.{aid}"
    notes = [f"arXiv id {aid} mapped to DataCite DOI {doi}"]
    first = text.strip().lower().split("/")[0].replace("arxiv:", "").strip()
    if not new and first != archive.lower():
        notes.append(f"subject class dropped: the arXiv id is {aid}")
    if version:
        notes.append(
            f"{version} requested, but arXiv DOIs are version-less: the latest "
            f"version is retrieved"
        )
    return doi, notes


@dataclass
class Item:
    """One requested article, as parsed from the caller's input."""

    input: object
    label: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    pii: str | None = None
    title: str | None = None  # expected title, used to cross-check (or to search)
    title_only: bool = False  # no identifier at all, only a title
    error: str | None = None  # set when the input cannot be understood
    notes: list = field(default_factory=list)


def _parse_string(text: str, item: Item) -> None:
    s = text.strip()
    if not s:
        item.error = "empty identifier"
        return
    if s.lower().startswith(
        (
            "http://",
            "https://",
            "www.",
            "doi.org/",
            "dx.doi.org/",
            "arxiv.org/",
            "export.arxiv.org/",
        )
    ):
        _parse_url(s, item)
        return
    ax = parse_arxiv(s)
    if ax:
        item.doi = ax[0]
        item.notes += ax[1]
        return
    if s.lower().startswith("arxiv"):
        item.error = (
            f"'{s}' is not a valid arXiv id (expected e.g. arXiv:2101.00001 or "
            f"hep-th/9901001)"
        )
        return
    m = PREFIX_RE.match(s)
    kind = m.group(1).lower() if m else None
    rest = s[m.end() :].strip() if m else s
    if kind == "pmid" or (kind is None and PMID_RE.match(rest)):
        if PMID_RE.match(rest):
            item.pmid = str(int(rest))
        else:
            item.error = f"'{s}' is not a valid PMID (PMIDs are 1-9 digits)"
        return
    if kind in ("pmcid", "pmc") or PMCID_RE.match(rest):
        cand = rest if rest.upper().startswith("PMC") else f"PMC{rest}"
        if PMCID_RE.match(cand):
            item.pmcid = cand.upper()
        else:
            item.error = f"'{s}' is not a valid PMCID (expected PMC followed by digits)"
        return
    if kind == "pii":
        item.pii = re.sub(r"[^0-9A-Z]", "", rest.upper())
        return
    if kind == "doi" or DOI_RE.match(rest):
        doi = clean_doi(rest)
        if doi:
            item.doi = doi
        else:
            item.error = f"'{s}' is not a valid DOI (DOIs look like 10.1234/suffix)"
        return
    if DOI_RE.search(s):  # a DOI embedded in a citation string
        item.doi = clean_doi(s)
        item.notes.append(
            "DOI extracted from a longer string; check it is the intended one"
        )
        return
    if len(s) >= 20 and len(s.split()) >= 4:
        item.title = s
        item.title_only = True
        return
    item.error = (
        f"could not recognise '{s}' as a PMID, PMCID, DOI or URL, and it is too "
        f"short to search as a title"
    )


def _parse_url(url: str, item: Item) -> None:
    u = url if "://" in url else "https://" + url
    for pat, kind in URL_PATTERNS:
        m = pat.search(u)
        if m:
            if kind == "pmid":
                item.pmid = m.group(1)
            elif kind == "pmcid":
                item.pmcid = m.group(1).upper()
            else:
                ax = parse_arxiv(unquote(m.group(1)))
                if not ax:
                    item.error = f"no valid arXiv id in URL {url!r}"
                    return
                item.doi = ax[0]
                item.notes += ax[1]
            return
    m = PII_RE.search(urlparse(u).path)
    if m:
        item.pii = m.group(1).upper()
        return
    parsed = urlparse(u)
    # Path first (doi.org/10.x/y, /doi/full/10.x/y); then each query value on its
    # own so '&utm_source=...' never ends up glued to the DOI.
    doi = clean_doi(parsed.path) or next(
        (
            d
            for d in (clean_doi(v.split("=", 1)[-1]) for v in parsed.query.split("&"))
            if d
        ),
        "",
    )
    if doi:
        item.doi = doi
        return
    item.error = (
        f"no PMID, PMCID, DOI or ScienceDirect PII found in URL {url!r}; open the "
        f"page and copy the DOI shown on it instead"
    )


def parse_item(raw: object) -> Item:
    """Parse one entry of a request: a string, or a dict with explicit fields."""
    if isinstance(raw, str):
        item = Item(input=raw)
        _parse_string(raw, item)
        return item
    if not isinstance(raw, dict):
        return Item(input=raw, error="each item must be a string or an object")
    item = Item(input=raw, label=raw.get("label"))
    title = (raw.get("title") or "").strip() or None
    given = {
        k: str(raw[k]).strip()
        for k in ("pmid", "pmcid", "doi", "arxiv", "url", "identifier")
        if raw.get(k) not in (None, "")
    }
    if not given:
        if title:
            _parse_string(title, item)
            if not item.title_only:  # the "title" was actually an identifier
                item.title = None
            return item
        item.error = (
            "no identifier given: provide pmid, doi, pmcid, arxiv, url or identifier"
        )
        return item
    errors = []
    for k, v in given.items():
        sub = Item(input=v)
        if k == "pmid":
            _parse_string(f"pmid:{v}", sub)
        elif k == "pmcid":
            _parse_string(f"pmcid:{v}", sub)
        elif k == "doi":
            _parse_string(f"doi:{v}", sub)
        elif k == "arxiv":
            _parse_string(v if v.lower().startswith("arxiv") else f"arxiv:{v}", sub)
        else:
            _parse_string(v, sub)
        if sub.error:
            errors.append(f"{k}: {sub.error}")
            continue
        if sub.title_only:
            errors.append(f"{k}: {v!r} is not an identifier (put titles in 'title')")
            continue
        for f in ("pmid", "pmcid", "doi", "pii"):
            new = getattr(sub, f)
            old = getattr(item, f)
            if new and old and new != old:
                errors.append(f"conflicting {f.upper()} values {old} and {new}")
            elif new:
                setattr(item, f, new)
        item.notes += sub.notes
    if errors:
        item.error = "; ".join(errors)
    item.title = title
    return item


def article_key(
    pmid: str | None = None, doi: str | None = None, pmcid: str | None = None
) -> str:
    """Stable key for an article: the PMID when there is one, else the DOI,
    else the PMCID."""
    if pmid:
        return pmid
    if doi:
        return "doi_" + re.sub(r"[^a-z0-9._-]+", "_", doi.lower()).strip("_")[:150]
    return pmcid or ""


def normalise_title(t: str | None) -> str:
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def title_matches(expected: str | None, actual: str | None) -> bool:
    """Loose title comparison: tolerant of case, punctuation, markup and truncation."""
    a, b = normalise_title(expected), normalise_title(actual)
    if not a or not b:
        return True
    if a == b or (len(a) >= 25 and (a in b or b in a)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85
