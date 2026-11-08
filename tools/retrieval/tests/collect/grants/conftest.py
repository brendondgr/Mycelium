"""Fixtures for the collection prototype tests.

Every fixture here is a stored raw payload shaped like the real thing, so the
whole pipeline below stage 1 runs with no network at all — which is the same
property the smoke checklist asserts about production.
"""

from __future__ import annotations

import pytest

from tools.retrieval.collect.core.rawstore import RawBundle
from tools.retrieval.collect.grants.pipeline import CollectConfig, Pipeline
from tools.retrieval.collect.grants.record import Opportunity


@pytest.fixture
def config(tmp_path) -> CollectConfig:
    return CollectConfig(root=tmp_path / "collect", sources=["grants_gov"])


@pytest.fixture
def pipeline(config) -> Pipeline:
    return Pipeline(config)


def bundle(source: str, records: list[dict], **meta) -> RawBundle:
    return RawBundle(
        source=source,
        run_id="20260101T000000Z",
        fetched_at="2026-01-01T00:00:00Z",
        records=records,
        meta=meta,
    )


def opportunity(**overrides) -> Opportunity:
    defaults = {
        "source": "grants_gov",
        "source_record_id": "1",
        "opportunity_number": "PA-25-001",
        "title": "A Study of Things",
        "funder": "National Institutes of Health",
        "description": "Long form description.",
        "close_date": "2027-01-01",
    }
    return Opportunity(**{**defaults, **overrides})


# --- realistic source payloads -------------------------------------------


GRANTS_GOV_SUMMARY = {
    "id": "357305",
    "number": "PAR-25-274",
    "title": "Feasibility Clinical Trials of Mind and Body Interventions",
    "agencyCode": "HHS-NIH11",
    "agency": "National Institutes of Health",
    "openDate": "01/17/2025",
    "closeDate": "11/17/2026",
    "oppStatus": "posted",
    "docType": "synopsis",
    "cfdaList": ["93.213"],
}

GRANTS_GOV_DETAIL = {
    "id": 357305,
    "opportunityNumber": "PAR-25-274",
    "opportunityTitle": "Feasibility Clinical Trials of Mind and Body Interventions",
    # Structured fields that were present in every real payload and never read.
    "topAgencyDetails": {"code": "HHS", "agencyName": "Department of Health and Human Services"},
    "agencyDetails": {"code": "HHS-NIH11", "agencyName": "National Institutes of Health"},
    "opportunityCategory": {"category": "D", "description": "Discretionary"},
    "cfdas": [{"cfdaNumber": "93.213"}],
    "synopsis": {
        "agencyName": "National Institutes of Health",
        "agencyCode": "HHS-NIH11",
        "synopsisDesc": "<p>The goal of this NOFO is to support feasibility trials.</p><ul><li>One</li><li>Two</li></ul>",
        "responseDate": "Nov 17, 2026 12:00:00 AM EST",
        "responseDateStr": "2026-11-17-00-00-00",
        "postingDateStr": "2024-11-21-00-00-00",
        "archiveDateStr": "2026-12-23-00-00-00",
        # Grants.gov writes the *string* "none" here constantly.
        "awardCeiling": "none",
        "awardFloor": "none",
        "applicantEligibilityDesc": "Other Eligible Applicants include the following.",
        "fundingInstruments": [{"description": "Grant"}],
        "applicantTypes": [
            {"description": "State governments"},
            {"description": "Small businesses"},
        ],
        "fundingActivityCategories": [{"description": "Health"}],
    },
}

#: A forecast record: payload lives under "forecast", not "synopsis".
GRANTS_GOV_FORECAST_SUMMARY = {
    "id": "355824",
    "number": "MP-CPI-25-001",
    "title": "Addressing Dementia Disparities",
    "agencyCode": "HHS-OPHS",
    "agency": "Office of the Assistant Secretary for Health",
    "openDate": "08/01/2026",
    "closeDate": "",
    "oppStatus": "forecasted",
    "docType": "forecast",
    "cfdaList": ["93.137"],
}

GRANTS_GOV_FORECAST_DETAIL = {
    "id": 355824,
    "forecast": {
        "forecastDesc": "<p>Forecast text.</p>",
        "estApplicationResponseDate": "Jun 23, 2027 12:00:00 AM EST",
        "estAwardFloor": "$50,000",
        "estAwardCeiling": "$250,000",
        "estNumberOfAwards": "3",
    },
}


SBIR_SOLICITATION = {
    "solicitation_title": "DoD SBIR 26.1 Annual",
    "solicitation_number": "DoD SBIR 26.1",
    "solicitation_id": "9001",
    "program": "SBIR",
    "phase": "Phase I",
    "agency": "Department of Defense",
    "branch": "Air Force",
    "solicitation_year": "2026",
    "release_date": "2026-01-05",
    "open_date": "2026-02-01",
    "close_date": "2026-12-18",
    "application_due_date": ["2026-12-18"],
    "current_status": "open",
    "solicitation_agency_url": "https://www.dodsbirsttr.mil/",
    "solicitation_topics": [
        {
            "topic_title": "Autonomous Undersea Navigation",
            "branch": "Navy",
            "topic_number": "N261-001",
            "topic_description": "Develop algorithms for GPS-denied undersea navigation.",
            "sbir_topic_link": "https://www.sbir.gov/topics/n261-001",
            "subtopics": [
                {
                    "subtopic_title": "Inertial drift correction",
                    "topic_number": "N261-001-A",
                    "topic_description": "Correct inertial drift over long transits.",
                }
            ],
        },
        {
            "topic_title": "Hypersonic Materials",
            "branch": "Air Force",
            "topic_number": "AF261-002",
            "topic_description": "Thermal protection systems for hypersonic vehicles.",
            "subtopics": [],
        },
    ],
}

#: Closed solicitation: must be filtered locally, since the endpoint offers no
#: reliable server-side status filter.
SBIR_CLOSED = {
    "solicitation_title": "Old Solicitation",
    "solicitation_number": "DoD SBIR 24.1",
    "solicitation_id": "8001",
    "agency": "Department of Defense",
    "current_status": "closed",
    "close_date": "2024-03-01",
    "solicitation_topics": [{"topic_title": "Nope", "topic_number": "X-1"}],
}


NIH_ANNOUNCEMENT = {
    "rowid": "41791",
    "PrimaryIC": "NCI",
    "Title": "Modular R01s in Cancer Control and Population Sciences",
    "Purpose": "This NOFO encourages applications for research in cancer control.",
    "RelNote": "",
    "ActivityCodes": "R01",
    "GuideLink": "http://grants.nih.gov/grants/guide/pa-files/PA-25-172.html",
    "RelDate": "2024-11-07",
    "AppReceiptDate": "Multiple dates, see announcement.",
    "IntentDate": "30 days prior to application due date.",
    "LARD": "2028-01-07",
    "DocType": "PA",
    "DocNum": "PA-25-172",
    "ExpirationDate": "2028-01-08",
    "DocStatus": "Published",
    "OpenDate": "01-05-2025",
    "PartIC": ["NCI", "NIA"],
    "RelatedNotices": ["PAR-24-122", "NOT-CA-25-006"],
}

NIH_OVERLAY_NOTICE = {
    "title": "Notice of Special Interest (NOSI): Research on Sleep and Cancer",
    "link": "https://grants.nih.gov/grants/guide/notice-files/NOT-CA-26-011.html",
    "description": "Notice NOT-CA-26-011 from the NIH Guide for Grants and Contracts",
    "pubDate": "Fri, 14 Aug 2026 02:33:00 EST",
    "body_html": (
        "<h1>NOT-CA-26-011</h1>"
        "<p>Notice Number: NOT-CA-26-011</p>"
        "<p>Key Dates Release Date: August 14, 2026</p>"
        "<p>First Available Due Date: October 05, 2026</p>"
        "<p>Expiration Date: January 08, 2029</p>"
        "<h2>Related Announcements</h2>"
        "<p>PA-25-172 - Modular R01s in Cancer Control and Population Sciences.</p>"
        "<p>PAR-24-122 - Another parent announcement.</p>"
        "<h2>Issued by</h2><p>National Cancer Institute ( NCI )</p>"
        "<h2>Purpose</h2><p>This Notice of Special Interest highlights interest in "
        "the relationship between sleep disruption and cancer outcomes.</p>"
    ),
}

#: A notice that names no parent at all. Must be flagged, not silently dropped.
NIH_ORPHAN_NOTICE = {
    "title": "Request for Information (RFI) on Peer Review",
    "link": "https://grants.nih.gov/grants/guide/notice-files/NOT-OD-26-088.html",
    "description": "Notice NOT-OD-26-088 from the NIH Guide for Grants and Contracts",
    "pubDate": "Fri, 14 Aug 2026 02:33:00 EST",
    "body_html": (
        "<p>Notice Number: NOT-OD-26-088</p>"
        "<p>Related Announcements None</p>"
        "<p>Issued by Office of The Director</p>"
        "<p>Purpose NIH seeks input.</p>"
        "<p>Expiration Date: December 31, 2027</p>"
    ),
}


NSF_UPCOMING_ITEM = {
    "feed": "upcoming",
    "title": "Biological Oceanography (BioOce)",
    "link": "https://www.nsf.gov/funding/opportunities/biooce-biological-oceanography/pd23-1650",
    "guid": "https://www.nsf.gov/funding/opportunities/biooce-biological-oceanography/pd23-1650",
    "description": (
        " Full Proposal Target Date: August 17, 2027<br/><br/>"
        "Program Guidelines: PD 23-1650<br/>"
        "<p>The Biological Oceanography Program supports fundamental research.</p>"
    ),
    "pubDate": "Mon, 03 Aug 2026 00:00:00 EST",
}

NSF_ROLLING_ITEM = {
    "feed": "announcements",
    "title": "Rapid Response Research (RAPID)",
    "link": "https://www.nsf.gov/funding/opportunities/rapid/999999",
    "guid": "https://www.nsf.gov/funding/opportunities/rapid/999999",
    "description": (
        "<P>Document Number: NSF 24-999<BR/>Full Proposal Accepted Anytime<BR/></P>"
        "<P>This is an NSF Program Description for rapid-response work.</P>"
    ),
    "pubDate": "Mon, 03 Aug 2026 00:00:00 EST",
}


EU_TOPIC = {
    "reference": "50132976TOPICSen",
    "url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-MSCA-2027-COFUND-01-01",
    "metadata": {
        "identifier": ["HORIZON-MSCA-2027-COFUND-01-01"],
        "title": ["MSCA COFUND 2027"],
        "callIdentifier": ["HORIZON-MSCA-2027-COFUND-01"],
        "deadlineDate": ["2027-04-06T00:00:00.000+0000"],
        "startDate": ["2026-12-08T00:00:00.000+0000"],
        "status": ["31094501"],
        "descriptionByte": ["<p>Expected Outcome:</p><ul><li>Deeper skills.</li></ul>"],
        "keywords": ["HORIZON-MSCA-2027-COFUND-01-01"],
        "typesOfAction": ["HORIZON TMA MSCA Cofund Doctoral programme"],
        "deadlineModel": ["single-stage"],
        "crossCuttingPriorities": ["AI", "DigitalAgenda"],
        # Admissibility boilerplate, near-identical across a whole programme.
        "topicConditions": [
            "<h4>Eligible countries</h4><p>Legal entities established in a Member State.</p>"
        ],
        "frameworkProgramme": ["43108390"],
        "budgetOverview": [
            '{"budgetTopicActionMap":{"112956":[{"action":"x","expectedGrants":4,'
            '"minContribution":1000000,"maxContribution":5000000,'
            '"budgetYearMap":{"2027":"51251165"}}]}}'
        ],
    },
}
