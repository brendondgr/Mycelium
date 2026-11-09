"""The fulltext tool's declaration. Standard library and spec imports only."""

from tools._framework.spec import Setting, Tool

#: The default order sources are tried in (the engine's DEFAULT_ORDER; a test
#: holds the two equal).
DEFAULT_SOURCES = [
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


def _key(key, help_, env):
    """A provider credential: a secret, read from the environment only."""
    return Setting(key, "str", "", help_, env=env, django=env, secret=True)


class FulltextTool(Tool):
    name = "fulltext"
    summary = (
        "Gets the paper itself: checks whether a legal copy of a paper can be "
        "reached, fetches it from PubMed Central, Europe PMC, arXiv, the "
        "open-access locators or (with the instance's keys) Elsevier, Springer "
        "Nature and Wiley, and keeps the original plus a markdown rendering."
    )
    #: Documents link to the corpus item they are the full text of.
    depends_on = ("retrieval",)
    settings = (
        Setting(
            "sources",
            "list",
            DEFAULT_SOURCES,
            "Sources to use, in the order they are tried. A keyed source "
            "without its key is skipped on its own.",
            env="FULLTEXT_SOURCES",
            django="FULLTEXT_SOURCES",
        ),
        Setting(
            "contact_email",
            "str",
            "",
            "Polite-pool address for NCBI, Crossref and OpenAlex; Unpaywall "
            "requires a real one. Empty uses SCRAPER_CONTACT_EMAIL.",
            env="FULLTEXT_CONTACT_EMAIL",
            django="FULLTEXT_CONTACT_EMAIL",
        ),
        Setting(
            "min_chars",
            "int",
            500,
            "Shortest body that counts as full text.",
            env="FULLTEXT_MIN_CHARS",
            django="FULLTEXT_MIN_CHARS",
        ),
        Setting(
            "concurrency",
            "int",
            4,
            "Articles fetched in parallel within one request (rate limits "
            "are enforced per source regardless).",
            env="FULLTEXT_CONCURRENCY",
            django="FULLTEXT_CONCURRENCY",
        ),
        Setting(
            "disable_ttl_hours",
            "float",
            6.0,
            "Hours a source switched off at runtime (quota, repeated "
            "refusals) stays off before it is tried again.",
            env="FULLTEXT_DISABLE_TTL_HOURS",
            django="FULLTEXT_DISABLE_TTL_HOURS",
        ),
        # The instance's publisher keys. Elsevier, Springer Nature and Wiley
        # are off without them; CORE works without its key, more slowly.
        _key(
            "elsevier_api_key",
            "Elsevier key (dev.elsevier.com). Full text also needs a subscribing "
            "network and the Article Retrieval API enabled by the library.",
            "ELSEVIER_API_KEY",
        ),
        _key(
            "elsevier_inst_token",
            "Elsevier institutional token: lets the key work off campus.",
            "ELSEVIER_INST_TOKEN",
        ),
        _key(
            "springer_api_key",
            "Springer Nature key (dev.springernature.com).",
            "SPRINGER_API_KEY",
        ),
        _key(
            "wiley_tdm_token",
            "Wiley text-and-data-mining token; works from a subscribing network.",
            "WILEY_TDM_TOKEN",
        ),
        _key(
            "core_api_key",
            "CORE key (core.ac.uk); optional, it only raises the rate limit.",
            "CORE_API_KEY",
        ),
    )
    health = "tools.fulltext.health:check"
    stages = ()
    mounts = ()  # no API yet; one comes later, inside this folder
