"""Phase C — all three normalizers return an identical AuthorProfileDraft shape."""

import dataclasses

from apps.accounts.intake.aggregate import aggregate
from apps.accounts.intake.drafts import AuthorProfileDraft
from apps.accounts.intake.normalizers import openalex, scholar, semantic

from .intake_fixtures import OPENALEX_RAW, SCHOLAR_RAW, SEMANTIC_RAW

DRAFTS = {
    "openalex": openalex.normalize(OPENALEX_RAW),
    "semantic": semantic.normalize(SEMANTIC_RAW),
    "scholar": scholar.normalize(SCHOLAR_RAW),
}


def test_all_normalizers_return_author_profile_draft() -> None:
    for draft in DRAFTS.values():
        assert isinstance(draft, AuthorProfileDraft)


def test_normalizers_agree_on_keys() -> None:
    key_sets = [set(dataclasses.asdict(d)) for d in DRAFTS.values()]
    assert key_sets[0] == key_sets[1] == key_sets[2]
    assert key_sets[0] == {
        "display_name",
        "institution",
        "areas",
        "keywords",
        "methods",
        "coauthors",
        "external_ids",
        "evidence",
    }


def test_each_source_extracts_core_signal() -> None:
    for source, draft in DRAFTS.items():
        assert draft.display_name == "Ada Lovelace", source
        assert draft.institution == "Analytical Engine Institute", source
        assert draft.areas, f"{source} produced no areas"
        assert draft.external_ids, f"{source} produced no external ids"
        assert draft.evidence, f"{source} produced no evidence"


def test_coauthors_exclude_the_author() -> None:
    for source, draft in DRAFTS.items():
        assert "Ada Lovelace" not in draft.coauthors, source


def test_aggregate_ranks_and_dedups_areas() -> None:
    # "Numerical Analysis" appears in both OpenAlex works -> ranked first, once.
    ranked = aggregate(DRAFTS["openalex"])
    assert ranked.areas[0] == "Numerical Analysis"
    assert ranked.areas.count("Numerical Analysis") == 1


def test_aggregate_preserves_draft_shape() -> None:
    before = set(dataclasses.asdict(DRAFTS["semantic"]))
    after = set(dataclasses.asdict(aggregate(DRAFTS["semantic"])))
    assert before == after
