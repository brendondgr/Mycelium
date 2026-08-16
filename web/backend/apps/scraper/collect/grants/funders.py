"""Canonical funder identity.

Sources name the same funder differently, and until they are reconciled a funder
filter silently splits one organisation into several and under-reports every one
of them. The measured case: NSF appears as "U.S. National Science Foundation"
(144 records, via Grants.gov) and "National Science Foundation" (24, via NSF's
own feed), so filtering on either name loses a third to a seventh of it.

The corpus supports **two** levels and conflating them would lose information in
the other direction:

* the **operating unit** — NIH, FDA, CDC, the Bureau of Land Management. This is
  what the ``funder`` field has always held and what a researcher means by "who
  funds this".
* the **department** — HHS, DOI, DOD. Rolling NIH's 665 records in with FDA and
  CDC under "Department of Health and Human Services" would make the facet less
  useful, not more, so the department is a second axis rather than a replacement.

Both are filterable. ``funder_canonical`` reconciles the operating-unit name and
``agency_code`` (populated in step 4) carries the department.
"""

from __future__ import annotations

import re

from apps.scraper.collect.grants.normalize import clean_text

#: Markers Grants.gov appends from its own internal systems. These are not part
#: of any funder's name — "Centers for Disease Control and Prevention - ERA" is
#: the CDC — and they fragment 232 records across otherwise identical names.
#:
#: Deliberately a list of *known system markers* rather than "strip anything
#: after a dash". "Department of Homeland Security - FEMA" would lose FEMA under
#: the general rule, and FEMA is the part that tells you who is funding.
_SYSTEM_SUFFIX = re.compile(
    r"\s*[-–—]{1,2}\s*(ERA(\s+Prod(uction)?)?|Grants\.gov|GRANTS\.GOV)\s*$",
    re.IGNORECASE,
)

#: Names that denote one funder under more than one string. Kept small and
#: evidence-driven: every entry here was measured as a real split in the corpus,
#: not guessed from plausibility. An alias table that grows on speculation starts
#: merging things that were never the same.
FUNDER_ALIASES: dict[str, str] = {
    "u s national science foundation": "National Science Foundation",
    "nsf": "National Science Foundation",
    "nasa headquarters": "National Aeronautics and Space Administration",
    "nasa": "National Aeronautics and Space Administration",
    "nih": "National Institutes of Health",
    "national institutes of health nih": "National Institutes of Health",
    "hhs national institutes of health": "National Institutes of Health",
    "european commission ec": "European Commission",
}

#: Department names for the codes step 4 recovered, so the second facet axis has
#: a label a reader recognizes rather than a four-letter code.
AGENCY_NAMES: dict[str, str] = {
    "HHS": "Health and Human Services",
    "DOD": "Defense",
    "DOS": "State",
    "DOI": "Interior",
    "USDOJ": "Justice",
    "DOJ": "Justice",
    "USDA": "Agriculture",
    "DOC": "Commerce",
    "DOT": "Transportation",
    "DOE": "Energy",
    "DOL": "Labor",
    "ED": "Education",
    "HUD": "Housing and Urban Development",
    "DHS": "Homeland Security",
    "VA": "Veterans Affairs",
    "TREAS": "Treasury",
    "NSF": "National Science Foundation",
    "NASA": "NASA",
    "EPA": "Environmental Protection Agency",
    "SBA": "Small Business Administration",
    "IMLS": "Institute of Museum and Library Services",
    "NEA": "National Endowment for the Arts",
    "NEH": "National Endowment for the Humanities",
    "SSA": "Social Security Administration",
    "USAID": "US Agency for International Development",
    "EC": "European Commission",
}

_NOISE = re.compile(r"[^a-z0-9]+")


def _alias_key(value: str) -> str:
    return _NOISE.sub(" ", value.lower()).strip()


def canonical_funder(funder: str, agency_code: str = "") -> str:
    """One name per funder, whichever source named it.

    Applies in order: strip the aggregator's system markers, then resolve known
    aliases. An unrecognized name is returned cleaned but otherwise untouched —
    the alternative, forcing it onto the nearest known funder, would merge
    organisations that merely read alike.
    """
    name = _SYSTEM_SUFFIX.sub("", clean_text(funder)).strip(" -–—")
    if not name:
        return AGENCY_NAMES.get(agency_code.upper(), "")
    return FUNDER_ALIASES.get(_alias_key(name), name)


def funder_id(funder: str, agency_code: str = "") -> str:
    """A stable slug for the canonical name, for grouping and URLs."""
    return _NOISE.sub("-", canonical_funder(funder, agency_code).lower()).strip("-")


def department(agency_code: str) -> str:
    """The department a code belongs to, or the bare code when unmapped.

    Returning the code rather than an empty string keeps the record groupable:
    an unmapped agency is still consistently itself, just without a friendly name.
    """
    code = clean_text(agency_code).upper()
    return AGENCY_NAMES.get(code, code)
