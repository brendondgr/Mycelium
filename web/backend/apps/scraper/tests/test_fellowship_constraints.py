"""The eligibility-prose extractor and the scrape-miss flag.

Pure Python: the pattern layer needs no model and no database, and the model
layer is exercised through its injected ``complete`` seam.
"""

from __future__ import annotations

from apps.scraper.pivot.fellowships.constraints import (
    extract_by_model,
    extract_by_pattern,
    is_resolved,
)
from apps.scraper.pivot.fellowships.parsers import empty_facets, facets_incomplete

# ---- Patterns ----------------------------------------------------------------


def test_received_the_phd_within_a_window():
    """The NSF class — the constraint that no facet can express."""
    out = extract_by_pattern(
        ["Applicants must have received the PhD within the previous two years."]
    )
    assert out["degree_required"] == "phd"
    assert out["min_stage"] == "postdoc"
    assert out["max_years_post_phd"] == 2
    assert out["source"] == "patterns"


def test_month_windows_round_up_to_whole_years():
    """Rounding down would gate an applicant the award would accept."""
    out = extract_by_pattern(
        ["Candidates must have earned a doctorate no more than 18 months prior."]
    )
    assert out["max_years_post_phd"] == 2


def test_doctoral_requirement_without_a_window():
    out = extract_by_pattern(["Applicants must hold a PhD at the time of award."])
    assert out["degree_required"] == "phd"
    assert out["min_stage"] == "postdoc"
    assert out["max_years_post_phd"] is None


def test_dissertation_stage_is_recognised():
    out = extract_by_pattern(
        ["Open to students who have advanced to candidacy and begun dissertation "
         "research."]
    )
    assert out["min_stage"] == "doctoral_dissertation"


def test_postdoctoral_appointment_phrasing():
    out = extract_by_pattern(
        ["The award supports a two-year postdoctoral research appointment."]
    )
    assert out["min_stage"] == "postdoc"


def test_an_award_duration_is_not_an_eligibility_window():
    """A window only counts inside a sentence that also requires the doctorate —
    otherwise "funding runs for no more than 3 years" becomes a fake gate."""
    out = extract_by_pattern(["Support is provided for no more than three years."])
    assert out["max_years_post_phd"] is None
    assert not is_resolved(out)


def test_silent_prose_constrains_nothing():
    out = extract_by_pattern(
        ["Applicants should submit two letters of recommendation."]
    )
    assert out == {
        "min_stage": "",
        "max_years_post_phd": None,
        "degree_required": "",
        "source": "none",
        "evidence": "",
    }


def test_empty_input_is_unconstrained():
    assert not is_resolved(extract_by_pattern([]))
    assert not is_resolved(extract_by_pattern(""))


# ---- The model layer ---------------------------------------------------------


def test_model_rows_are_validated_and_indexed():
    units = [("A", "prose a"), ("B", "prose b")]
    raw = (
        '{"items": [{"item": 1, "min_stage": "postdoc", "max_years_post_phd": 3,'
        ' "degree_required": "phd", "evidence": "within three years of the PhD"},'
        ' {"item": 2, "min_stage": "nonsense", "max_years_post_phd": null,'
        ' "degree_required": "", "evidence": ""}]}'
    )
    out = extract_by_model(units, complete=lambda _p: raw)
    assert out[0]["min_stage"] == "postdoc"
    assert out[0]["max_years_post_phd"] == 3
    assert out[0]["source"] == "llm"
    # Row 2 resolved nothing usable, so it is not reported at all.
    assert 1 not in out


def test_model_failure_degrades_to_nothing():
    def boom(_prompt):
        raise RuntimeError("model down")

    assert extract_by_model([("A", "prose")], complete=boom) == {}
    assert extract_by_model([("A", "prose")], complete=lambda _p: "not json") == {}
    assert extract_by_model([], complete=lambda _p: "") == {}


def test_model_cannot_invent_an_out_of_range_item():
    out = extract_by_model(
        [("A", "prose")],
        complete=lambda _p: '{"items": [{"item": 7, "min_stage": "postdoc"}]}',
    )
    assert out == {}


# ---- The scrape-miss flag ----------------------------------------------------


def test_facets_incomplete_detects_an_empty_record():
    assert facets_incomplete(empty_facets()) is True


def test_an_unrecognized_category_is_not_eligibility_information():
    facets = empty_facets()
    facets["other"] = ["Some new site category"]
    assert facets_incomplete(facets) is True


def test_a_record_with_any_facet_is_complete():
    facets = empty_facets()
    facets["field"] = ["Humanities"]
    assert facets_incomplete(facets) is False
