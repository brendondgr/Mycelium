"""Tests for the fellowships parsers — adapted from the ProQuest tool's
``tests/test_fellowships.py``.

Tests are pure-Python (no DB, no Django, no network). They cover deadline
parsing (incl. anticipated/previous-deadline/MM-YYYY), amount parsing (incl.
ranges/up-to/K-M suffixes/currency), category bucketing (incl. unknown → other),
derive_flags, classify_award, and the deadline_status helper.
"""

from tools.retrieval.eligibility.parsers import (
    bucket_categories,
    classify_award,
    deadline_status,
    derive_flags,
    parse_amount,
    parse_deadline,
)

# ---------------------------------------------------------------------------
# parse_amount — currency + kind across the real formats seen on the site
# ---------------------------------------------------------------------------


def test_amount_up_to_usd():
    a = parse_amount("Up to $25,000")
    assert a["kind"] == "up_to"
    assert a["currency"] == "USD"
    assert a["min"] is None
    assert a["max"] == 25000


def test_amount_range_usd_no_commas():
    a = parse_amount("$3000-6,000")
    assert (a["kind"], a["min"], a["max"]) == ("range", 3000, 6000)


def test_amount_foreign_currency_codes_and_symbols():
    assert parse_amount("Up to KRW 13,800,000")["currency"] == "KRW"
    assert parse_amount("JPY 8,888,000 + Travel")["currency"] == "JPY"
    assert parse_amount("NT $56,000 - $336,000")["currency"] == "TWD"
    assert parse_amount("CAD $5,000 - $50,000")["currency"] == "CAD"
    assert parse_amount("€26,040 - $€41,550")["currency"] == "EUR"
    assert parse_amount("Up to NIS 92,412 + travel")["currency"] == "ILS"


def test_amount_k_suffix():
    a = parse_amount("$62K Salary + Benefits")
    assert a["max"] == 62000


def test_amount_open_min():
    open_min = parse_amount("$75,000+")
    assert open_min["kind"] == "range"
    assert open_min["min"] == 75000
    assert open_min["max"] is None


def test_amount_varies_when_no_number():
    a = parse_amount("Stipend + Benefits")
    assert a["kind"] == "varies"
    assert a["min"] is None and a["max"] is None


def test_amount_unknown_when_empty():
    a = parse_amount("")
    assert a["kind"] == "unknown"


def test_amount_keeps_raw_and_note():
    a = parse_amount("Varies", note="US $20,000 annually (adjusted ...)")
    assert a["raw"] == "Varies"
    assert "20,000" in a["note"]


# ---------------------------------------------------------------------------
# parse_deadline — YYYY-MM vs YYYY-MM-DD, types, previous deadline
# ---------------------------------------------------------------------------


def test_deadline_continuous():
    d = parse_deadline("Continuous")
    assert d["type"] == "continuous" and d["date"] == ""


def test_deadline_anticipated_month_only():
    d = parse_deadline("Anticipated 04/2027")
    assert d["type"] == "anticipated" and d["date"] == "2027-04"


def test_deadline_true_full_date():
    d = parse_deadline("07/13/2026")
    assert d["type"] == "true" and d["date"] == "2026-07-13"


def test_deadline_mm_yyyy_format():
    d = parse_deadline("09/2026")
    assert d["type"] == "true" and d["date"] == "2026-09"


def test_deadline_previous_is_split_out():
    d = parse_deadline("Anticipated 04/2027 ( Previous deadline 04/30/2026 )")
    assert d["date"] == "2027-04"
    assert d["previous_date"] == "2026-04-30"


def test_deadline_suspended_status():
    d = parse_deadline("Suspended")
    assert d["type"] == "suspended" and d["date"] == ""


def test_deadline_rolling():
    d = parse_deadline("Rolling")
    assert d["type"] == "rolling" and d["date"] == ""


def test_deadline_varies():
    d = parse_deadline("Varies by program")
    assert d["type"] == "varies" and d["date"] == ""


def test_deadline_unknown_text():
    d = parse_deadline("TBD")
    assert d["type"] == "unknown" and d["date"] == ""


# ---------------------------------------------------------------------------
# facets + flags + classification
# ---------------------------------------------------------------------------


def test_bucket_categories_and_other():
    cats = ("Sciences/Engineering/Math; International Students; Master's; "
            "Fellowship/Grant; Some New Category")
    f = bucket_categories(cats)
    assert f["field"] == ["Sciences/Engineering/Math"]
    assert f["citizenship"] == ["International Students"]
    assert f["stage"] == ["Master's"]
    assert f["award_type"] == ["Fellowship/Grant"]
    assert f["other"] == ["Some New Category"]


def test_bucket_categories_from_list():
    f = bucket_categories(["Humanities", "Women", "Postdoctoral/Post-graduate"])
    assert f["field"] == ["Humanities"]
    assert f["limits"] == ["Women"]
    assert f["stage"] == ["Postdoctoral/Post-graduate"]


def test_bucket_categories_empty():
    f = bucket_categories("")
    assert all(v == [] for v in f.values())


def test_bucket_categories_unknown_to_other():
    f = bucket_categories("Completely Unknown Category")
    assert "Completely Unknown Category" in f["other"]
    assert f["field"] == []


def test_flags_require_us_when_no_international():
    us_only = bucket_categories(
        "US Citizens, Nationals, or Permanent Residents; Master's"
    )
    assert derive_flags(us_only)["requires_us_citizenship"] is True


def test_flags_not_require_us_when_both():
    both = bucket_categories(
        "US Citizens, Nationals, or Permanent Residents; International Students"
    )
    assert derive_flags(both)["requires_us_citizenship"] is False
    assert derive_flags(both)["open_to_international"] is True


def test_flags_doctoral_stages():
    f = bucket_categories("Dissertation Research; Dissertation Write-Up")
    flags = derive_flags(f)
    assert flags["doctoral"] is True
    assert flags["masters"] is False
    assert flags["postdoc"] is False


def test_flags_postdoc():
    f = bucket_categories("Postdoctoral/Post-graduate")
    flags = derive_flags(f)
    assert flags["postdoc"] is True
    assert flags["doctoral"] is False


def test_classify_award_priority():
    assert classify_award("ACM - Graduate Fellowship for Women") == "fellowship"
    assert classify_award("Academy - Graduate Scholarships") == "scholarship"
    assert classify_award("Academy - Jessup Short-Term Research Awards") == "award"
    assert classify_award("American Academy in Rome - Rome Prize") == "prize"
    assert classify_award("Some Foundation - Research Grants") == "grant"


def test_classify_award_default_fellowship():
    # A title with no matching keywords defaults to "fellowship"
    assert classify_award("Some Unknown Program Name") == "fellowship"


def test_classify_award_internship_from_facet():
    f = bucket_categories("Research Internships")
    assert classify_award("Some Program", f) == "internship"


# ---------------------------------------------------------------------------
# deadline_status helper
# ---------------------------------------------------------------------------

TODAY = "2026-07-06"


def test_deadline_status_open_rolling():
    d = {"type": "rolling", "date": ""}
    s = deadline_status(d, TODAY)
    assert s["status"] == "open"


def test_deadline_status_open_continuous():
    d = {"type": "continuous", "date": ""}
    s = deadline_status(d, TODAY)
    assert s["status"] == "open"


def test_deadline_status_open_anticipated():
    d = {"type": "anticipated", "date": "2027-04"}
    s = deadline_status(d, TODAY)
    assert s["status"] == "open"


def test_deadline_status_closed_suspended():
    d = {"type": "suspended", "date": ""}
    s = deadline_status(d, TODAY)
    assert s["status"] == "closed"


def test_deadline_status_open_future_true():
    d = {"type": "true", "date": "2026-12-31"}
    s = deadline_status(d, TODAY)
    assert s["status"] == "open"
    assert "2026-12-31" in s["summary"]


def test_deadline_status_closed_past_true():
    d = {"type": "true", "date": "2025-01-01"}
    s = deadline_status(d, TODAY)
    assert s["status"] == "closed"


def test_deadline_status_open_future_month_only():
    # YYYY-MM coerced to YYYY-MM-01 — a future month should be "open"
    d = {"type": "true", "date": "2027-04"}
    s = deadline_status(d, TODAY)
    assert s["status"] == "open"


def test_deadline_status_unknown_for_no_date():
    d = {"type": "unknown", "date": ""}
    s = deadline_status(d, TODAY)
    assert s["status"] == "unknown"


def test_deadline_status_empty_dict():
    s = deadline_status({}, TODAY)
    assert s["status"] == "unknown"
