"""The fulltext tool's declaration. Standard library and spec imports only."""

from tools._framework.spec import Tool


class FulltextTool(Tool):
    name = "fulltext"
    summary = (
        "Gets the paper itself: checks whether a legal copy of a paper can be "
        "reached, fetches it from PubMed Central, Europe PMC, arXiv, the "
        "open-access locators or (with the instance's keys) Elsevier, Springer "
        "Nature and Wiley, and keeps the original plus a markdown rendering."
    )
    #: Documents link to the corpus item they are the full text of (Phase 3).
    depends_on = ("retrieval",)
    settings = ()
    stages = ()
    mounts = ()  # no API yet; one comes later, inside this folder
