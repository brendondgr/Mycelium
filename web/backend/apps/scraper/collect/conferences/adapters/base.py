"""The contract every conference source adapter implements.

Two methods, and they are not allowed to know about each other. ``fetch`` talks
to the network and returns raw payloads; ``parse`` takes those payloads and
returns canonical records without touching the network. Keeping the seam sharp is
what makes the parse and resolve stages re-runnable offline — which matters more
here than in the funding pipeline, because the resolve stage gets re-run every
time a trust threshold is tuned.

``fetch`` is explicitly allowed to make many requests, and several adapters must:
OpenReview needs three batched stages because stage three depends on stage two's
*payload*, and WikiCFP needs one request per event. What ``fetch`` may not do is
interpret. It writes down what the source said.
"""

from __future__ import annotations

from typing import Any, Protocol

from apps.scraper.collect.conferences.record import ConferenceInstance, ConferenceSeries
from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle


class ConferenceAdapter(Protocol):
    #: Stable identifier, used as the raw filename, the ``source`` field, and the
    #: CLI selector.
    name: str

    #: True when this source publishes the venue's *own* record — the organisers'
    #: words rather than a third party's transcription. The conference analogue
    #: of ``funder_native``. Merge precedence gives these descriptive fields.
    venue_native: bool

    #: Build phase, for the phased-rollout CLI.
    phase: int

    #: Reuse terms, carried onto every record this adapter emits so a later
    #: licensing decision can filter rather than force a re-fetch.
    license: str

    def available(self) -> tuple[bool, str]:
        """(enabled, reason). A gated source reports why it is off."""
        ...

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """Network only. Returns raw payloads; interprets nothing."""
        ...

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        """Raw payload to canonical records. Must not touch the network."""
        ...


class BaseConferenceAdapter:
    """Shared defaults. Adapters subclass this and override the two real methods."""

    name = "base"
    venue_native = False
    phase = 99
    license = ""

    def available(self) -> tuple[bool, str]:
        return True, ""

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        raise NotImplementedError

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
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
