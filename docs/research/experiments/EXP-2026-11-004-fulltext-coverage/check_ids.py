"""EXP-2026-11-004 follow-up: are the corpus's stored PubMed identifiers the paper's own?

    python3 <exp>/check_ids.py      (stdlib only; one PubMed efetch)

For every sampled paper with a PMID, fetches the PubMed record and compares the
stored DOI and PMCID with the article's *own* ids (PubmedData/ArticleIdList,
not the ReferenceList's cited papers). Writes data/corpus_ids.json.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def main() -> None:
    sample = json.loads((HERE / "data" / "sample.json").read_text())
    pm = [s for s in sample if s["identifier"].get("pmid")]
    body = urllib.parse.urlencode({
        "db": "pubmed", "retmode": "xml", "tool": "mycelium-fulltext",
        "id": ",".join(s["identifier"]["pmid"] for s in pm),
    }).encode()
    with urllib.request.urlopen(EFETCH, body, timeout=60) as resp:
        root = ET.fromstring(resp.read())
    own = {}
    for a in root.iter("PubmedArticle"):
        ids = {x.get("IdType"): (x.text or "").lower()
               for x in a.findall("PubmedData/ArticleIdList/ArticleId")}
        refs = len(a.findall("PubmedData/ReferenceList//ArticleId"))
        own[a.findtext("MedlineCitation/PMID")] = (ids, refs)

    doi_bad = pmc_bad = no_own_doi_with_refs = 0
    by_source: Counter = Counter()
    for s in pm:
        ident = s["identifier"]
        ids, refs = own.get(ident["pmid"], ({}, 0))
        if ident.get("doi") and ids.get("doi") and ident["doi"].lower() != ids["doi"]:
            doi_bad += 1
            by_source[s["corpus_source"]] += 1
        if ident.get("pmcid") and ident["pmcid"].upper() != (ids.get("pmc") or "").upper():
            pmc_bad += 1
        if not ids.get("doi") and refs:
            no_own_doi_with_refs += 1
    out = {
        "sampled_with_pmid": len(pm),
        "pubmed_answered": len(own),
        "stored_doi_differs_from_pubmed_own": doi_bad,
        "stored_pmcid_differs_from_pubmed_own": pmc_bad,
        "no_own_doi_but_reference_dois": no_own_doi_with_refs,
        "doi_differs_by_corpus_source": dict(by_source),
    }
    (HERE / "data" / "corpus_ids.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
