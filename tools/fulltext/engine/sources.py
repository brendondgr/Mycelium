"""The source registry, endpoints, limits, and credential lookup.

One row per provider. The engine reads credentials from a plain mapping (the
``env`` every class here takes), keyed by the names below; the Django side of
the tool fills it from the instance's settings.

Credential names:

==========================  =================================================
``CONTACT_EMAIL``           polite-pool address for NCBI, Crossref, OpenAlex;
                            required by Unpaywall (it rejects placeholders)
``PUBMED_API_KEY``          optional, raises the NCBI limit to 10 req/s
``OPEN_ALEX_API_KEY``       optional, raises the OpenAlex limit
``SEMANTIC_SCHOLAR_API_KEY`` optional, raises the Semantic Scholar limit
``CORE_API_KEY``            optional, raises the CORE limit
``ELSEVIER_API_KEY``        turns Elsevier on (+ ``ELSEVIER_INST_TOKEN``)
``SPRINGER_API_KEY``        turns Springer Nature on
``WILEY_TDM_TOKEN``         turns Wiley on
==========================  =================================================
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping

IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNPAYWALL = "https://api.unpaywall.org/v2/"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
ELSEVIER = "https://api.elsevier.com/content/article/doi/"
ELSEVIER_SEARCH = "https://api.elsevier.com/content/search/sciencedirect"
SPRINGER_OA = "https://api.springernature.com/openaccess/jats"
SPRINGER_TDM = "https://api.springernature.com/meta/v2/jats"
WILEY_TDM = "https://api.wiley.com/onlinelibrary/tdm/v1/articles/"
CROSSREF = "https://api.crossref.org/works/"
CORE = "https://api.core.ac.uk/v3/search/works"
OPENALEX = "https://api.openalex.org/works/"
DATACITE = "https://api.datacite.org/dois/"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_PDF = (
    "https://export.arxiv.org/pdf/"  # arXiv asks for programmatic access via export.
)
ARXIV_DOI = "10.48550/arxiv."  # DataCite DOI prefix of every arXiv paper
S2 = "https://api.semanticscholar.org/graph/v1/paper/"

#: Providers do not agree on how to say "you are out of quota". Wiley says it
#: with an HTTP 500 whose JSON body carries policies.ratelimit.QuotaViolation,
#: which looks exactly like a transient server error unless you read the body.
QUOTA_RE = re.compile(
    r"quota\s*(limit|violation)|QuotaViolation|rate limit quota|quota\s*exceeded", re.I
)
WILEY_PREFIXES = ("10.1002/", "10.1111/")  # DOI prefixes the Wiley TDM API serves
BODY_DEADLINE = 180  # seconds to receive a whole response body
MAX_BODY = 200 * 2**20  # bytes; nothing legitimate here is larger
ENTITLEMENT_STRIKES = 25  # consecutive 401/403s before a source is switched off
USER_AGENT = "mycelium-fulltext/1.0 (Mycelium research assistant; full-text tool)"
#: The NCBI E-utilities ``tool`` parameter.
NCBI_TOOL = "mycelium-fulltext"

PLACEHOLDER = re.compile(r"(your_|example\.com|changeme|xxx+|<.*>)", re.I)

#: The keyed sources whose content is licensed to the instance's institution
#: rather than openly available. Springer counts only when its subscription
#: endpoint served the paper (the provenance says which).
LICENSED_SOURCES = frozenset({"elsevier", "wiley", "crossref"})

SOURCES: OrderedDict[str, dict] = OrderedDict(
    [
        (
            "pmc",
            dict(
                label="PubMed Central (NCBI efetch)",
                needs=[],
                optional=["PUBMED_API_KEY"],
                interval=0.0,
            ),
        ),
        (
            "europepmc",
            dict(
                label="Europe PMC full-text XML", needs=[], optional=[], interval=0.15
            ),
        ),
        (
            "elsevier",
            dict(
                label="Elsevier ScienceDirect Article Retrieval API",
                needs=["ELSEVIER_API_KEY"],
                optional=["ELSEVIER_INST_TOKEN"],
                interval=0.2,
            ),
        ),
        (
            "springer",
            dict(
                label="Springer Nature full-text / OA JATS API",
                needs=["SPRINGER_API_KEY"],
                optional=[],
                interval=0.35,
            ),
        ),
        (
            "wiley",
            dict(
                label="Wiley TDM API (PDF)",
                needs=["WILEY_TDM_TOKEN"],
                optional=[],
                interval=0.5,
            ),
        ),
        # arXiv: one request per 3 s, PDFs included.
        (
            "arxiv",
            dict(
                label="arXiv (PDF from export.arxiv.org)",
                needs=[],
                optional=[],
                interval=3.0,
            ),
        ),
        (
            "crossref",
            dict(
                label="Crossref text-mining links (publisher sites)",
                needs=[],
                optional=[],
                interval=0.15,
            ),
        ),
        (
            "core",
            dict(
                label="CORE aggregator",
                needs=[],
                optional=["CORE_API_KEY"],
                interval=0.45,
                interval_nokey=6.5,
            ),
        ),
        (
            "unpaywall",
            dict(
                label="Unpaywall OA locator + download",
                needs=["CONTACT_EMAIL"],
                optional=[],
                interval=0.12,
            ),
        ),
        (
            "openalex",
            dict(
                label="OpenAlex OA locator + download",
                needs=[],
                optional=["OPEN_ALEX_API_KEY"],
                interval=0.12,
            ),
        ),
        (
            "semanticscholar",
            dict(
                label="Semantic Scholar OA PDF + download",
                needs=[],
                optional=["SEMANTIC_SCHOLAR_API_KEY"],
                interval=0.8,
                interval_nokey=3.2,
            ),
        ),
    ]
)
DEFAULT_ORDER = [
    "pmc",
    "europepmc",
    "elsevier",
    "springer",
    "wiley",
    "arxiv",
    "unpaywall",
    "openalex",
    "crossref",
    "core",
    "semanticscholar",
]
assert set(DEFAULT_ORDER) == set(SOURCES)

#: Sources that need a key the operator must supply to work at all.
KEYED_SOURCES = frozenset(
    s for s, spec in SOURCES.items() if any(k != "CONTACT_EMAIL" for k in spec["needs"])
)


def cfg(env: Mapping[str, str] | None, key: str) -> str | None:
    """A credential, or None when it is blank or still a placeholder."""
    v = str((env or {}).get(key) or "").strip().strip('"').strip("'")
    return None if not v or PLACEHOLDER.search(v) else v


def arxiv_id(doi: str | None) -> str | None:
    """'hep-th/9901001' or '2101.00001' for an arXiv DOI, else None."""
    d = (doi or "").lower()
    if not d.startswith(ARXIV_DOI):
        return None
    return d[len(ARXIV_DOI) :] or None


def missing_credentials(env: Mapping[str, str] | None, source: str) -> list[str]:
    """The credentials ``source`` needs that ``env`` lacks."""
    return [k for k in SOURCES[source]["needs"] if not cfg(env, k)]
