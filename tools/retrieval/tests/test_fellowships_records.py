"""Tests for :func:`tools.retrieval.fellowships.records.build_fellowship_item`.

Covers: field mapping from real records, grant exclusion, YYYY-MM coercion,
prune_after only for true hard-dated deadlines, and missing-id rejection.

Records are inline dicts taken from the real fellowships.json output (3 records
representing true, anticipated, and continuous deadline types).

Relocated from ``test_pivot_records.py``'s fellowship coverage (plan Phase 6 —
the deletion of Pivot-RP): ``build_pivot_item`` used to dispatch on an ``area``
string across three unrelated record shapes; ``build_fellowship_item`` is the
fellowship branch alone, with no area parameter at all, so the old
``test_unknown_area_raises`` case has no equivalent here — every record this
function sees is a fellowship, always.
"""

from tools.retrieval.fellowships.records import build_fellowship_item

TODAY = "2026-07-06"

# ---------------------------------------------------------------------------
# Inline fixtures (real records from fellowships.json — simplified)
# ---------------------------------------------------------------------------

# Record with a true hard deadline — scholarship award_class.
_SCHOLARSHIP = {
    "id": "4137",
    "source": "illinois-fellowship-finder",
    "source_url": "https://fellowship-finder.grad.illinois.edu/SearchResult/Fellowship/4137",
    "external_url": "https://www.americanheraldry.org/education-resources/william-barton-scholarship/",
    "title": "American Heraldry Society - William Barton Graduate Scholarship",
    "award_class": "scholarship",
    "deadline": {
        "type": "true",
        "date": "2026-07-31",
        "previous_date": "",
        "raw": "07/31/2026",
    },
    "award_amount": {
        "kind": "exact",
        "currency": "USD",
        "min": 1500,
        "max": 1500,
        "raw": "$1,500",
        "note": "Up to $1,500.",
    },
    "eligibility": [
        "Be graduate or undergraduate students in any field.",
        "Apply once they have reached the thesis prospectus stage.",
    ],
    "facets": {
        "field": ["Social Sciences", "Fine Arts", "Humanities"],
        "citizenship": [
            "US Citizens, Nationals, or Permanent Residents",
            "International Students",
        ],
        "stage": ["Master's", "Dissertation Research", "Dissertation Write-Up"],
        "award_type": ["Fellowship/Grant"],
        "limits": [],
        "other": [],
    },
    "flags": {
        "requires_us_citizenship": False,
        "open_to_international": True,
        "masters": True,
        "doctoral": True,
        "postdoc": False,
    },
    "description": "Barton Scholarships support master's and doctoral students.",
    "blurb": "Scholarship for research on coats of arms.",
    "note": "",
    "contact_email": "secretary@americanheraldry.org",
    "scraped_at": "2026-07-06T22:20:13+00:00",
}

# Record with an anticipated YYYY-MM deadline — fellowship award_class.
_FELLOWSHIP_ANTICIPATED = {
    "id": "5128",
    "source": "illinois-fellowship-finder",
    "source_url": "https://fellowship-finder.grad.illinois.edu/SearchResult/Fellowship/5128",
    "external_url": "http://www.aauw.org/international-fellowships/",
    "title": "AAUW - International Fellowships for Graduate Students",
    "award_class": "fellowship",
    "deadline": {
        "type": "anticipated",
        "date": "2026-09",
        "previous_date": "2025-09-30",
        "raw": "Anticipated 09/2026 ( Previous deadline 09/30/2025 )",
    },
    "award_amount": {
        "kind": "up_to",
        "currency": "USD",
        "min": None,
        "max": 25000,
        "raw": "Up to $25,000",
        "note": "Master's: $20,000. Doctoral: $25,000.",
    },
    "eligibility": [
        "Identify as women who are neither U.S. citizens nor permanent residents.",
        "Be admitted or enrolled full-time in their first master's or doctoral degree.",
    ],
    "facets": {
        "field": ["Social Sciences", "Sciences/Engineering/Math", "Humanities"],
        "citizenship": ["International Students"],
        "stage": [
            "Master's", "Early Years of Doctoral Program", "Dissertation Research"
        ],
        "award_type": ["Fellowship/Grant"],
        "limits": ["Women", "Annual stipend of at least $10,000"],
        "other": [],
    },
    "flags": {
        "requires_us_citizenship": False,
        "open_to_international": True,
        "masters": True,
        "doctoral": True,
        "postdoc": False,
    },
    "description": "AAUW Fellowships support women pursuing graduate study.",
    "blurb": "Fellowships for women international students.",
    "note": "",
    "contact_email": "awards@aauw.org",
    "scraped_at": "2026-07-06T22:20:13+00:00",
}

# Record with a continuous deadline — award award_class, no prune_after.
_CONTINUOUS = {
    "id": "3581",
    "source": "illinois-fellowship-finder",
    "source_url": "https://fellowship-finder.grad.illinois.edu/SearchResult/Fellowship/3581",
    "external_url": "http://www.ansp.org/research/fellowships-endowments/jessup-mchenry/",
    "title": "Academy of Natural Sciences - Jessup Short-Term Research Awards",
    "award_class": "award",
    "deadline": {
        "type": "continuous",
        "date": "",
        "previous_date": "",
        "raw": "Continuous",
    },
    "award_amount": {
        "kind": "varies",
        "currency": "",
        "min": None,
        "max": None,
        "raw": "Varies",
        "note": "",
    },
    "eligibility": [
        "Applicants may be pre-doctoral or postdoctoral researchers.",
        "Grants support short-term visits to ANSP collections.",
    ],
    "facets": {
        "field": ["Sciences/Engineering/Math"],
        "citizenship": [
            "US Citizens, Nationals, or Permanent Residents",
            "International Students",
        ],
        "stage": ["Dissertation Research", "Postdoctoral/Post-graduate"],
        "award_type": ["Short-Term Travel"],
        "limits": [],
        "other": [],
    },
    "flags": {
        "requires_us_citizenship": False,
        "open_to_international": True,
        "masters": False,
        "doctoral": True,
        "postdoc": True,
    },
    "description": "Jessup and McHenry awards support short-term visiting fellowships.",
    "blurb": "Short-term visiting awards to the Academy collections.",
    "note": "",
    "contact_email": "grants@ansp.org",
    "scraped_at": "2026-07-06T22:20:13+00:00",
}

# A grant record that must be excluded.
_GRANT_RECORD = {
    "id": "9999",
    "source": "illinois-fellowship-finder",
    "source_url": (
        "https://fellowship-finder.grad.illinois.edu/SearchResult/Fellowship/9999"
    ),
    "external_url": "https://example.com",
    "title": "Some Foundation - Research Grant",
    "award_class": "grant",
    "deadline": {
        "type": "true", "date": "2026-12-01", "previous_date": "", "raw": "12/01/2026",
    },
    "award_amount": {
        "kind": "exact", "currency": "USD", "min": 10000, "max": 10000,
        "raw": "$10,000", "note": "",
    },
    "eligibility": [],
    "facets": {
        "field": [], "citizenship": [], "stage": [],
        "award_type": [], "limits": [], "other": [],
    },
    "flags": {
        "requires_us_citizenship": False, "open_to_international": False,
        "masters": False, "doctoral": False, "postdoc": False,
    },
    "description": "", "blurb": "", "note": "", "contact_email": "",
    "scraped_at": "2026-07-06T22:20:13+00:00",
}


# ---------------------------------------------------------------------------
# build_fellowship_item — field mapping
# ---------------------------------------------------------------------------


def test_scholarship_item_maps_fields():
    item = build_fellowship_item(_SCHOLARSHIP, today=TODAY)
    assert item is not None
    assert item.type == "fellowship"
    assert item.external_id == "4137"
    assert "William Barton" in item.title
    assert item.subtitle == "Scholarship"  # award_class title-cased
    assert item.source == "illinois-fellowship-finder"
    # metadata keys
    assert item.metadata["award_class"] == "scholarship"
    assert item.metadata["deadline_date"] == "2026-07-31"
    assert item.metadata["deadline_type"] == "true"
    assert item.metadata["amount_kind"] == "exact"
    assert item.metadata["amount_currency"] == "USD"
    assert item.metadata["amount_min"] == 1500
    assert item.metadata["amount_max"] == 1500
    assert item.metadata["external_url"] == "https://www.americanheraldry.org/education-resources/william-barton-scholarship/"
    assert item.metadata["website"] == item.metadata["external_url"]
    assert item.metadata["next_kind"] == "application"
    assert item.metadata["status"] == "open"
    assert isinstance(item.metadata["eligibility"], list)
    assert len(item.metadata["eligibility"]) == 2
    assert isinstance(item.metadata["facets"], dict)
    assert "Social Sciences" in item.metadata["facets"]["field"]


def test_scholarship_true_deadline_sets_prune_after():
    item = build_fellowship_item(_SCHOLARSHIP, today=TODAY)
    # True hard deadline with YYYY-MM-DD → prune_after is set.
    assert item.metadata["prune_after"] == "2026-07-31"


def test_anticipated_fellowship_coerces_yyyy_mm():
    item = build_fellowship_item(_FELLOWSHIP_ANTICIPATED, today=TODAY)
    assert item is not None
    # YYYY-MM coerced to first-of-month for deadline_date.
    assert item.metadata["deadline_date"] == "2026-09-01"
    assert item.metadata["deadline_type"] == "anticipated"


def test_anticipated_fellowship_no_prune_after():
    item = build_fellowship_item(_FELLOWSHIP_ANTICIPATED, today=TODAY)
    # Anticipated deadline → prune_after is "" (rolling/anticipated are kept).
    assert item.metadata["prune_after"] == ""
    assert item.metadata["next_kind"] == "application"


def test_continuous_deadline_no_deadline_date_no_prune_after():
    item = build_fellowship_item(_CONTINUOUS, today=TODAY)
    assert item is not None
    assert item.metadata["deadline_date"] == ""
    assert item.metadata["prune_after"] == ""
    assert item.metadata["next_kind"] == ""
    assert item.metadata["status"] == "open"  # continuous is open


def test_grant_exclusion_returns_none():
    item = build_fellowship_item(_GRANT_RECORD, today=TODAY)
    assert item is None, "grant records on the fellowship site must be excluded"


def test_missing_id_returns_none():
    rec = dict(_SCHOLARSHIP, id="")
    assert build_fellowship_item(rec, today=TODAY) is None


def test_record_text_includes_key_fields():
    item = build_fellowship_item(_SCHOLARSHIP, today=TODAY)
    text = item.text.lower()
    assert "heraldry" in text or "scholarship" in text.lower()
    # Facet strings in the text.
    assert "social sciences" in text or "humanities" in text
