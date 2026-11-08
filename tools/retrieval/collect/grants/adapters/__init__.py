"""Adapter registry, ordered by build phase.

Phases are strictly sequential in the briefing, and the registry keeps that
visible: ``--phase 2`` enables everything up to and including P2, so a partial
rollout is a flag rather than a code edit.
"""

from __future__ import annotations

from tools.retrieval.collect.grants.adapters.base import Adapter, BaseAdapter
from tools.retrieval.collect.grants.adapters.eu_portal import EUPortalAdapter
from tools.retrieval.collect.grants.adapters.grants_gov import GrantsGovAdapter
from tools.retrieval.collect.grants.adapters.nih_guide import NIHGuideAdapter
from tools.retrieval.collect.grants.adapters.nsf import NSFAdapter
from tools.retrieval.collect.grants.adapters.sam_gov import SAMGovAdapter
from tools.retrieval.collect.grants.adapters.sbir import SBIRAdapter

__all__ = [
    "Adapter",
    "BaseAdapter",
    "EUPortalAdapter",
    "GrantsGovAdapter",
    "NIHGuideAdapter",
    "NSFAdapter",
    "SAMGovAdapter",
    "SBIRAdapter",
    "build_registry",
    "funder_native_sources",
]


def build_registry() -> dict[str, Adapter]:
    adapters: list[Adapter] = [
        GrantsGovAdapter(),  # P0
        SBIRAdapter(),  # P1
        NIHGuideAdapter(),  # P3
        NSFAdapter(),  # P4
        EUPortalAdapter(),  # P5
        SAMGovAdapter(),  # P6
    ]
    return {adapter.name: adapter for adapter in adapters}


def adapters_for_phase(phase: int) -> list[str]:
    return [name for name, adapter in build_registry().items() if adapter.phase <= phase]


def funder_native_sources() -> frozenset[str]:
    """Sources that publish the funder's own long-form text.

    Merge precedence reads this: these win descriptive fields, aggregators win
    structured dates and money.
    """
    return frozenset(
        name for name, adapter in build_registry().items() if adapter.funder_native
    )
