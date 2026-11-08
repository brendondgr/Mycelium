"""The contract every source adapter implements.

Two methods, and they are not allowed to know about each other. ``fetch`` talks to
the network and returns raw payloads; ``parse`` takes those payloads and returns
canonical records without touching the network. Keeping the seam sharp is what
makes stage 2 re-runnable offline.
"""

from __future__ import annotations

from typing import Any, Protocol

from tools.retrieval.collect.core.http import PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle
from tools.retrieval.collect.grants.record import Opportunity


class Adapter(Protocol):
    #: Stable identifier, used as the raw filename, the ``source`` field, and the
    #: CLI selector.
    name: str

    #: True when this source publishes the funder's own long-form text. Dedupe
    #: merge policy gives these precedence for descriptive fields; aggregators
    #: win on structured dates and money instead.
    funder_native: bool

    #: Build phase this adapter belongs to, for the phased-rollout CLI.
    phase: int

    def available(self) -> tuple[bool, str]:
        """(enabled, reason). A key-gated source reports why it is off."""
        ...

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """Network only. Returns raw payloads; does nothing else."""
        ...

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        """Raw payload to canonical records. Must not touch the network."""
        ...


class BaseAdapter:
    """Shared defaults. Adapters subclass this and override the two real methods."""

    name = "base"
    funder_native = False
    phase = 99

    def available(self) -> tuple[bool, str]:
        return True, ""

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        raise NotImplementedError

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        raise NotImplementedError

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def bundle(
        source: str,
        run_id: str,
        fetched_at: str,
        records: list[dict[str, Any]],
        **meta: Any,
    ) -> RawBundle:
        return RawBundle(
            source=source, run_id=run_id, fetched_at=fetched_at, records=records, meta=meta
        )
