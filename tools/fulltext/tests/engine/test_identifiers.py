import pytest

from tools.fulltext.engine.identifiers import (
    article_key,
    clean_doi,
    parse_item,
    title_matches,
)


@pytest.mark.parametrize(
    "raw, field, value",
    [
        ("31234567", "pmid", "31234567"),
        ("PMID: 31234567", "pmid", "31234567"),
        ("pmc7286232", "pmcid", "PMC7286232"),
        ("PMCID:PMC7286232", "pmcid", "PMC7286232"),
        ("10.1016/J.WATRES.2020.116073", "doi", "10.1016/j.watres.2020.116073"),
        ("doi: 10.1002/tox.222.", "doi", "10.1002/tox.222"),
        (
            "https://doi.org/10.1016/s1085-5629(99)80036-4",
            "doi",
            "10.1016/s1085-5629(99)80036-4",
        ),
        ("https://pubmed.ncbi.nlm.nih.gov/31234567/", "pmid", "31234567"),
        (
            "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7286232/",
            "pmcid",
            "PMC7286232",
        ),
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC7286232/", "pmcid", "PMC7286232"),
        ("https://europepmc.org/article/MED/31234567", "pmid", "31234567"),
        (
            "https://onlinelibrary.wiley.com/doi/full/10.1002/tox.222",
            "doi",
            "10.1002/tox.222",
        ),
        (
            "https://link.springer.com/article/10.1007/s11356-020-1?utm_source=x",
            "doi",
            "10.1007/s11356-020-1",
        ),
        (
            "https://www.sciencedirect.com/science/article/pii/S0048969720314170",
            "pii",
            "S0048969720314170",
        ),
        ("arXiv:2101.00001", "doi", "10.48550/arxiv.2101.00001"),
        ("hep-th/9901001", "doi", "10.48550/arxiv.hep-th/9901001"),
        ("arxiv.org/abs/hep-th/9901001v3", "doi", "10.48550/arxiv.hep-th/9901001"),
        ("https://arxiv.org/pdf/2101.00001v1.pdf", "doi", "10.48550/arxiv.2101.00001"),
        ({"arxiv": "0704.0001"}, "doi", "10.48550/arxiv.0704.0001"),
    ],
)
def test_string_forms(raw, field, value):
    item = parse_item(raw)
    assert item.error is None
    assert getattr(item, field) == value


def test_doi_in_prose_keeps_balanced_parens_and_drops_trailing_ones():
    assert (
        clean_doi("(see 10.1016/s1085-5629(99)80036-4)")
        == "10.1016/s1085-5629(99)80036-4"
    )


def test_title_string_is_a_title_search():
    item = parse_item("Microplastics in the human brain and their effects")
    assert item.title_only and item.title.startswith("Microplastics")


@pytest.mark.parametrize(
    "raw", ["", "abc", "1234567890", "PMCxyz", {"pmid": "12a"}, {}, 42]
)
def test_garbage_is_rejected_with_a_reason(raw):
    item = parse_item(raw)
    assert item.error


def test_object_fields_merge_and_conflicts_are_caught():
    item = parse_item(
        {
            "pmid": "111",
            "doi": "https://doi.org/10.1016/j.envpol.2020.111",
            "title": "Microplastics in the brain",
            "label": "ref-1",
        }
    )
    assert (item.pmid, item.doi, item.label) == (
        "111",
        "10.1016/j.envpol.2020.111",
        "ref-1",
    )
    assert item.title == "Microplastics in the brain" and not item.title_only
    bad = parse_item({"pmid": "111", "identifier": "222"})
    assert "conflicting PMID" in bad.error


def test_title_matching_tolerates_case_markup_and_truncation():
    full = "Microplastics in the brain: a <i>systematic</i> review of exposure pathways"
    assert title_matches("MICROPLASTICS IN THE BRAIN: A SYSTEMATIC REVIEW", full)
    assert title_matches(
        "Microplastics in the brain - a systematic review of exposure pathways.", full
    )
    assert not title_matches("Nanoplastics and cardiovascular outcomes in adults", full)


def test_article_key():
    assert article_key("111", "10.1/x") == "111"
    assert (
        article_key(None, "10.1016/S1085-5629(99)80036-4")
        == "doi_10.1016_s1085-5629_99_80036-4"
    )
