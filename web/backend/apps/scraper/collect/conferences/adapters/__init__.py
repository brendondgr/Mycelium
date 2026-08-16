"""Adapter registry, ordered by build phase.

The briefing's phases are strictly sequential and the registry keeps that
visible: ``--phase 2`` enables everything up to and including P2, so a partial
rollout is a flag rather than a code edit.

The ordering is not arbitrary. The structured repository comes first because it
is already correct, so the multi-round and timezone models get proven against
clean data.

**WikiCFP is deliberately not registered here** (plan decision D5). Its
``Crawl-delay: 5`` makes a full pull ~3.9h, it is user-submitted with a large
predatory-spam share, and it lands in ``resolve.COMMUNITY_SOURCES`` — trust
tier C, quarantined from default output — so the records it would add never
surface. ``resolve.py``'s ``COMMUNITY_SOURCES`` still names ``"wikicfp"``
because ``openresearch`` alone still needs that tier-C branch; only the
adapter (the thing that would make 2,811 requests) is gone.
"""

from __future__ import annotations

from apps.scraper.collect.conferences.adapters.ams_mathcal import AMSMathCalAdapter
from apps.scraper.collect.conferences.adapters.base import (
    BaseConferenceAdapter,
    ConferenceAdapter,
)
from apps.scraper.collect.conferences.adapters.ccf_deadlines import CCFDeadlinesAdapter
from apps.scraper.collect.conferences.adapters.miccai import MICCAIAdapter
from apps.scraper.collect.conferences.adapters.openresearch import OpenResearchAdapter
from apps.scraper.collect.conferences.adapters.openreview import OpenReviewAdapter
from apps.scraper.collect.conferences.adapters.society_pages import SocietyPagesAdapter

__all__ = [
    "AMSMathCalAdapter",
    "BaseConferenceAdapter",
    "CCFDeadlinesAdapter",
    "ConferenceAdapter",
    "MICCAIAdapter",
    "OpenResearchAdapter",
    "OpenReviewAdapter",
    "SocietyPagesAdapter",
    "adapters_for_phase",
    "build_registry",
    "venue_native_sources",
]

#: ConfIDent, Wikidata and ConfRef were probed and deliberately not built:
#: ConfIDent has 6 live future submission deadlines against OpenResearch's 342
#: (the DFG-funded flagship is a curiosity, not a source); Wikidata has no
#: deadline property at all (the data model has nowhere to put one -- P8968,
#: P12655 and P12998 are the only "submission"/"deadline"-labelled properties
#: in the whole knowledge base, none of them a date); ConfRef.org's host
#: resolves but refuses every connection (DNS up, TCP dead across three
#: independent attempts). See docs/conferences/recon/scholarly_event_metadata.md.


def build_registry() -> dict[str, ConferenceAdapter]:
    adapters: list[ConferenceAdapter] = [
        CCFDeadlinesAdapter(),  # P0  structured deadline repository
        OpenReviewAdapter(),  # P2  peer-review platform
        # WikiCFPAdapter() dropped (D5) — see the module docstring.
        OpenResearchAdapter(),  # P3  open scholarly event metadata
        MICCAIAdapter(),  # P4  society calendar
        AMSMathCalAdapter(),  # P4  society calendar
        SocietyPagesAdapter(),  # P4  society "dates and deadlines" page registry
    ]
    return {adapter.name: adapter for adapter in adapters}


def adapters_for_phase(phase: int) -> list[str]:
    return [name for name, adapter in build_registry().items() if adapter.phase <= phase]


def venue_native_sources() -> frozenset[str]:
    """Sources publishing the venue's own record rather than a transcription.

    Merge precedence reads this: these win descriptive fields.
    """
    return frozenset(
        name for name, adapter in build_registry().items() if adapter.venue_native
    )


def license_for(source: str) -> str:
    adapter = build_registry().get(source)
    return adapter.license if adapter else ""
