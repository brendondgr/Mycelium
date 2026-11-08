"""Decide which sources to ask for one article, and explain the outcome in words.

Routing is driven by what is known about the article after resolution:

* a PMCID means PubMed Central has a deposit, so PMC (then Europe PMC) go first;
* the DOI prefix names the publisher, which decides whether a publisher
  text-mining API applies (Elsevier 10.1016, Wiley 10.1002/10.1111, Springer
  Nature 10.1007/...), and arXiv preprints (10.48550/arxiv.) go to arxiv.org;
* any DOI can be looked up in the open-access locators (Unpaywall, OpenAlex,
  Crossref, CORE, Semantic Scholar);
* sources missing credentials, or switched off at runtime (quota,
  entitlement), are skipped with the reason recorded.

The plan never changes what a source does; it only skips the ones that cannot
help, so a request never spends Wiley's daily quota on an Elsevier paper.
"""

from __future__ import annotations

from .sources import SOURCES, WILEY_PREFIXES

# DOI prefix -> (publisher, the keyed source that serves it, or None)
PUBLISHERS = [
    (
        ("10.1016/", "10.1006/", "10.1053/", "10.1054/", "10.1067/", "10.1078/"),
        "Elsevier",
        "elsevier",
    ),
    (WILEY_PREFIXES, "Wiley", "wiley"),
    (
        ("10.1007/", "10.1038/", "10.1186/", "10.1140/", "10.1245/"),
        "Springer Nature",
        "springer",
    ),
    (("10.1021/",), "American Chemical Society", None),
    (("10.1039/",), "Royal Society of Chemistry", None),
    (("10.1080/",), "Taylor & Francis", None),
    (("10.1093/",), "Oxford University Press", None),
    (("10.1177/",), "SAGE", None),
    (("10.1097/",), "Wolters Kluwer", None),
    (("10.1089/",), "Mary Ann Liebert", None),
    (("10.1088/",), "IOP Publishing", None),
    (("10.3390/",), "MDPI (open access)", None),
    (("10.3389/",), "Frontiers (open access)", None),
    (("10.1371/",), "PLOS (open access)", None),
    (("10.1101/",), "bioRxiv / medRxiv (preprint)", None),
    (("10.48550/arxiv.",), "arXiv (preprint)", "arxiv"),
]
PUBLISHER_SOURCES = {"elsevier", "wiley", "springer", "arxiv"}
DOI_SOURCES = {"crossref", "core", "unpaywall", "openalex", "semanticscholar"}


def publisher_of(doi: str | None) -> tuple[str | None, str | None]:
    """(publisher name, keyed source or None) for a DOI, from its prefix."""
    d = (doi or "").lower()
    for prefixes, name, source in PUBLISHERS:
        if d.startswith(prefixes):
            return name, source
    if d:
        return f"publisher with DOI prefix {d.split('/')[0]}", None
    return None, None


def plan(disabled: dict[str, str], pmid, doi, pmcid, order) -> list[dict]:
    """Ordered list of {source, action: try|skip, reason} for one resolved article.

    ``disabled`` is ``{source: reason}`` for sources that cannot be asked now
    (:attr:`Fetcher.disabled`).
    """
    publisher, owner = publisher_of(doi)
    steps = []
    for s in order:
        label = SOURCES[s]["label"]
        if s in PUBLISHER_SOURCES and doi and owner != s:
            steps.append(
                dict(
                    source=s,
                    action="skip",
                    reason=f"article is published by {publisher}, not "
                    f"{label.split()[0]}",
                )
            )
        elif s in disabled:
            reason = disabled[s]
            steps.append(
                dict(
                    source=s,
                    action="skip",
                    reason=reason
                    if reason.startswith("missing")
                    else f"switched off: {reason}",
                )
            )
        elif s == "pmc":
            if pmcid:
                steps.append(
                    dict(
                        source=s,
                        action="try",
                        reason=f"deposited in PubMed Central as {pmcid}",
                    )
                )
            else:
                steps.append(
                    dict(
                        source=s,
                        action="skip",
                        reason="no PubMed Central deposit for this article",
                    )
                )
        elif s == "europepmc":
            if pmcid or pmid:
                steps.append(
                    dict(
                        source=s,
                        action="try",
                        reason="Europe PMC mirrors PMC and some preprints",
                    )
                )
            else:
                steps.append(
                    dict(source=s, action="skip", reason="needs a PMID or PMCID")
                )
        elif s in PUBLISHER_SOURCES:
            if not doi:
                steps.append(dict(source=s, action="skip", reason="needs a DOI"))
            else:
                steps.append(
                    dict(source=s, action="try", reason=f"{publisher} DOI -> {label}")
                )
        elif s in DOI_SOURCES:
            if doi:
                steps.append(
                    dict(source=s, action="try", reason=f"look up DOI in {label}")
                )
            else:
                steps.append(dict(source=s, action="skip", reason="needs a DOI"))
    return steps


# --------------------------------------------------------------------------- #
# Explaining an outcome
# --------------------------------------------------------------------------- #
RETRY_HINT = "retry the request later"
RETRYABLE_MARKERS = ("quota", "error", "http 5", "http 429", "rate", "retry tomorrow")
NOTE_WORDS = [  # fetcher outcome code -> words for a person
    ("no-id", "has no record of it"),
    ("no-doi", "needs a DOI"),
    ("not-found", "does not know this DOI"),
    ("closed", "knows no open-access copy"),
    ("no-links", "lists no full-text links"),
    ("needs-key", "only links to the publisher's own API"),
    ("no-body", "returned a page without the article text"),
    ("http 404", "does not hold this article (HTTP 404)"),
    ("http 403", "refused access (HTTP 403)"),
    ("http 401", "rejected our credentials (HTTP 401)"),
    ("not-wiley", "does not publish this article"),
]


def humanise(note: str | None) -> str:
    """A fetcher outcome note ('closed (cached)', 'http 404; ...') in words."""
    out: list[str] = []
    for part in (note or "").replace(" (cached)", "").split("; "):
        words = next((w for code, w in NOTE_WORDS if part.startswith(code)), None)
        if words and words not in out:
            out.append(words)
        elif not words and part.startswith("http "):
            out.append(f"answered HTTP {part[5:]}")
        elif not words and part:
            out.append(part)
    return ", ".join(out) or "no answer"


def _label(source: str) -> str:
    return SOURCES[source]["label"].split(" (")[0]


def explain(publisher_name, owner, steps, tried, source=None, chars=0):
    """(explanation, retryable, next_steps) for one article's fetch result."""
    if source:
        label = SOURCES[source]["label"]
        return f"Full text retrieved from {label} ({chars:,} characters).", False, []

    parts: list[str] = []
    next_steps: list[str] = []
    retryable = False
    tried_any = [s for s in steps if s["action"] == "try"]
    if not tried_any:
        parts.append(
            "No source could be asked: the article has no DOI and no PubMed "
            "Central deposit, and every other source needs a DOI."
        )
        next_steps.append("If the article has a DOI, resend the request with it.")

    for note in (tried or {}).values():
        n = (note or "").lower()
        if any(m in n for m in RETRYABLE_MARKERS):
            retryable = True

    # The publisher-specific story, which is usually the real reason.
    if owner:
        note = (tried or {}).get(owner, "")
        step = next((s for s in steps if s["source"] == owner), None)
        if step and step["action"] == "skip":
            parts.append(
                f"The article is published by {publisher_name}, but its API was "
                f"not used ({step['reason']})."
            )
            if "quota" in step["reason"]:
                retryable = True
                next_steps.append(
                    f"{publisher_name}'s daily quota resets; {RETRY_HINT} "
                    f"(tomorrow) and only the missing articles are asked again."
                )
            elif step["reason"].startswith("missing"):
                next_steps.append(
                    f"The instance has no {publisher_name} key; an operator "
                    f"can add one to turn this source on."
                )
        elif owner == "elsevier" and ("403" in note or "not entitled" in note):
            parts.append(
                "Elsevier owns this article and refused the full text: the "
                "instance's Elsevier key is not entitled to the full-text Article "
                "Retrieval API (a library TDM agreement)."
            )
            next_steps.append(
                "The library must enable Elsevier full-text API access for "
                "the instance's key, or supply ELSEVIER_INST_TOKEN."
            )
        elif "403" in note and owner == "wiley":
            parts.append(
                "Wiley owns this article and refused it: Wiley authorises by IP, "
                "and this server is not on a subscribing network."
            )
            next_steps.append("Run Mycelium on the campus network or VPN, then retry.")
        elif owner == "arxiv":
            parts.append(
                f"The article is an arXiv preprint, but arXiv did not supply a "
                f"usable PDF: it {humanise(note)}."
            )
            if "no-body" in note:
                next_steps.append(
                    "The PDF may be withdrawn or scanned images only; check "
                    "the abstract page at arxiv.org/abs/<id>."
                )
        elif owner == "springer" and note.startswith("not-found"):
            parts.append(
                "Springer Nature's open-access API has no copy of it, and the "
                "instance's key does not cover Springer subscription content."
            )
        elif "quota" in note:
            parts.append(f"{publisher_name}'s API quota ran out during this request.")
            retryable = True
            next_steps.append(
                f"{RETRY_HINT.capitalize()} (the quota resets daily); "
                f"already-retrieved articles are not asked again."
            )
        elif note:
            parts.append(f"{publisher_name}'s API {humanise(note)}.")
    elif publisher_name:
        parts.append(
            f"The article is published by {publisher_name}, which offers no "
            f"self-serve text-mining API, so only an open-access copy could have "
            f"been used."
        )

    oa_notes = {
        s: (tried or {}).get(s)
        for s in (
            "unpaywall",
            "openalex",
            "semanticscholar",
            "core",
            "crossref",
            "europepmc",
        )
        if (tried or {}).get(s)
    }
    if oa_notes:
        closed = [
            s for s, n in oa_notes.items() if n and ("closed" in n or "not-found" in n)
        ]
        if "unpaywall" in closed or "openalex" in closed:
            parts.append("Unpaywall/OpenAlex report no legal open-access copy.")
        failed = {
            s: n
            for s, n in oa_notes.items()
            if s not in closed and "needs-key" not in n
        }
        if failed:
            parts.append(
                "Also tried: "
                + "; ".join(f"{_label(s)} {humanise(n)}" for s, n in failed.items())
                + "."
            )
    if retryable and not any("retry" in x.lower() for x in next_steps):
        next_steps.append(
            f"Some failures were transient (rate limits / server errors); "
            f"{RETRY_HINT} may succeed."
        )
    if not next_steps:
        next_steps.append("Use the abstract, or obtain the PDF through the library.")
    return (
        " ".join(parts) or "No source returned a full-text body.",
        retryable,
        next_steps,
    )
